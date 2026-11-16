"""临时 PostgreSQL 表验证业务快照和 HTTP 取数，不调用供应商或改写业务数据。"""

import copy
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from store import SqlStore
from test_knowledge_flow import add_source
from test_knowledge_flow import environment as environment

from tender.api.analysis import routes as analysis_api
from tender.api.knowledge import routes as knowledge
from tender.api.shared.errors import install_error_handlers
from tender.application.analysis import service as analysis
from tender.application.analysis.data import (
    BusinessRecord,
    display_items,
    module_data,
    prepare_records,
)
from tender.application.analysis.data_store import publish_data_snapshot
from tender.application.knowledge.content import encode

pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证"
)

COMMON = {"kind": "common", "lot_refs": []}


@pytest.fixture
def basis(environment):
    request, conn, pid = environment
    add_source(conn, pid, (
        "本项目分为A标段、B标段。所有标段须提供营业执照。"
        "A标段质保三年。B标段质保五年。补遗：A标段质保四年。"
    ))
    analysis_api.save_settings(pid, analysis_api.AnalysisSettings(category="goods"), request)
    created = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    store = knowledge.store(request)
    # 夹具与终态断言要写测试 schema：直连同一批临时表，但展示与发布仍走仓储。
    db = SqlStore(store.engine, store.company_id)
    source = db.sources(db.collections_for_project(pid))[0]
    block = db.readable_chunks(source)[0]

    def record(key, title, content, *, kind="requirement", lot=None, code=None):
        return BusinessRecord(
            key=key, title=title, text=content, kind=kind, code=code,
            scope={"kind": "lots", "lot_refs": [lot]} if lot else COMMON,
            structuring="complete",
            citations=[{"block_id": block["block_id"], "quote": content}],
        )

    state = {}
    items = prepare_records([
        record("lot-a", "A标段", "A标段", kind="lot", code="A"),
        record("lot-b", "B标段", "B标段", kind="lot", code="B"),
        record("common", "证明材料", "所有标段须提供营业执照"),
        record("a", "质保期", "A标段质保三年", lot="A"),
        record("b", "质保期", "B标段质保五年", lot="B"),
    ], state, {block["block_id"]: block}, "project_basic_info_parsing")
    for item in items:
        item["verification"] = "supported"
    state.update(staged_items=items, staged_items_verified=True)
    business = module_data(state)
    module_id = conn.execute(text("""INSERT INTO analysis_module
        (report_id,module_key,title,status,items,business_data)
        VALUES (:report,'project_basic_info_parsing','项目概况','completed',
                CAST(:items AS JSONB),CAST(:business AS JSONB)) RETURNING id"""), {
            "report": created["id"], "items": encode(display_items(items)),
            "business": encode(business),
        }).scalar_one()
    db.execute("UPDATE analysis_report SET status='completed',finished_at=now() WHERE id=:id",
               {"id": created["id"]})
    app = FastAPI()
    app.state.components = request.app.state.components
    app.include_router(knowledge.router)
    app.include_router(analysis_api.router)
    install_error_handlers(app)
    with TestClient(app) as client:
        yield SimpleNamespace(
            request=request, conn=conn, project_id=pid, db=db, report_id=created["id"],
            module_id=module_id, state=state, business=business, client=client,
            path=f"/api/v1/analysis/reports/{created['id']}",
            source=source, block=block,
        )


def test_lot_without_original_code_publishes_and_resolves_by_verified_name(basis):
    state = {}
    records = [
        BusinessRecord(
            key="named-lot", title="A标段", text="A标段", kind="lot", scope=COMMON,
            citations=[{"block_id": basis.block["block_id"], "quote": "A标段"}],
        ),
        BusinessRecord(
            key="warranty", title="质保要求", text="A标段质保三年", kind="requirement",
            scope={"kind": "lots", "lot_refs": ["A标段"]}, structuring="complete",
            citations=[{"block_id": basis.block["block_id"], "quote": "A标段质保三年"}],
        ),
    ]
    items = prepare_records(records, state, {basis.block["block_id"]: basis.block},
                            "project_basic_info_parsing")
    for item in items:
        item["verification"] = "supported"
    state["staged_items"] = items
    basis.db.execute(
        "UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
        {"data": encode(module_data(state)), "id": basis.module_id},
    )
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    assert publish_data_snapshot(basis.db, basis.report_id)["id"] == snapshot["id"]
    lot = snapshot["data"]["lots"][0]
    assert lot["title"] == "A标段" and lot["code"] is None
    response = basis.client.post(basis.path + "/context", json={
        "snapshot_id": snapshot["id"], "purpose": "check", "lot_id": lot["lot_id"],
    })
    assert response.status_code == 200
    requirement = response.json()["requirements"][0]
    assert requirement["scope"]["lot_ids"] == [lot["lot_id"]]
    assert requirement["citations"][0]["element_id"] == basis.block["element_id"]


def test_independent_module_json_uses_separate_evidence_and_live_permissions(basis):
    path = basis.path + "/modules/project_basic_info_parsing/records"
    response = basis.client.get(path)
    assert response.status_code == 200
    result = response.json()
    assert len(result["records"]) == 5
    assert result["output_schema"]["sections"][2] == {
        "title": "项目基本信息", "layout": "table", "columns": ["字段", "内容"],
        "scalar_columns": ["字段"], "title_column": "字段",
    }
    assert all("citations" not in r for r in result["records"])
    record = next(r for r in result["records"] if r["key"] == "a")
    refs = [result["evidence"][key] for key in record["evidence_ids"]]
    # 原文由服务端按实际已读块生成；模型传入的旧quote不再决定引用范围。
    assert refs[0]["quote"] == basis.block["content"]
    assert refs[0]["element_id"] == basis.block["element_id"]
    # 独立数据入口同样检查实时依据，删除来源后不能绕过报告权限读取正文。
    basis.db.execute("DELETE FROM knowledge_source WHERE id=:id", {"id": basis.source["source_id"]})
    hidden = basis.client.get(path).json()
    assert hidden["records"] == [] and hidden["evidence"] == {}
    assert basis.client.get(basis.path + "/modules/unknown/records").status_code == 404


def test_terminal_snapshot_is_idempotent_and_context_is_single_lot(basis):
    assert basis.client.get(basis.path + "/data").status_code == 409
    basis.db.execute("UPDATE analysis_report SET status='running' WHERE id=:id",
                     {"id": basis.report_id})
    assert publish_data_snapshot(basis.db, basis.report_id) is None
    basis.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id",
                     {"id": basis.report_id})
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    assert publish_data_snapshot(basis.db, basis.report_id)["id"] == snapshot["id"]
    loaded = basis.client.get(basis.path + "/data").json()
    assert loaded["stale"] is False
    assert loaded["snapshot_id"] == snapshot["id"]
    lots = {lot["code"]: lot["lot_id"] for lot in loaded["data"]["lots"]}
    request = {"snapshot_id": snapshot["id"], "purpose": "check", "limit": 1}
    missing = basis.client.post(basis.path + "/context", json=request)
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "lot_selection_required"
    request["lot_id"] = lots["A"]
    first = basis.client.post(basis.path + "/context", json=request).json()
    assert first["total_requirements"] == 2
    second = basis.client.post(basis.path + "/context", json={
        **request, "offset": first["next_offset"],
    }).json()
    assert second["next_offset"] is None
    assert first["requirement_manifest"] == second["requirement_manifest"]
    assert {r["key"] for r in first["requirements"] + second["requirements"]} == {"common", "a"}
    invalid = basis.client.post(basis.path + "/context", json={**request, "lot_id": 999999})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "invalid_lot"
    b_id = next(r["id"] for r in loaded["data"]["requirements"] if r["key"] == "b")
    wrong_requirement = basis.client.post(basis.path + "/context", json={
        **request, "purpose": "content", "requirement_ids": [b_id],
    })
    assert wrong_requirement.status_code == 422
    assert wrong_requirement.json()["error"]["code"] == "invalid_requirements"


@pytest.mark.parametrize("staged", [False, True])
def test_report_keeps_business_identity_and_never_exposes_internal_payload(basis, staged):
    if staged:
        basis.db.execute("UPDATE analysis_module SET status='partial',items='[]' WHERE id=:id",
                         {"id": basis.module_id})
        basis.conn.execute(text("""INSERT INTO agent_module_run
            (module_id,company_id,attempt,thread_id,status,limits,state)
            VALUES (:module,1,1,'business-stage','failed','{}',CAST(:state AS JSONB))"""), {
                "module": basis.module_id, "state": encode(basis.state),
            })
    module = basis.client.get(basis.path).json()["modules"][0]
    items = module["items"]
    assert len([item for item in items if item["field"] == "质保期"]) == 2
    assert {item["record_id"] for item in items} == {r["id"] for r in basis.business["records"]}
    assert "business_data" not in module
    assert all("business" not in item for item in items)


def test_new_revision_preserves_history_and_rejects_old_or_foreign_snapshot(basis):
    first = publish_data_snapshot(basis.db, basis.report_id)
    business = copy.deepcopy(basis.business)
    corrected = next(r for r in business["records"] if r["key"] == "a")
    corrected["text"] = "A标段质保四年"
    business["evidence"][corrected["evidence_ids"][0]]["quote"] = corrected["text"]
    basis.db.execute("UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
                     {"data": encode(business), "id": basis.module_id})
    second = publish_data_snapshot(basis.db, basis.report_id)
    assert second["revision"] == first["revision"] + 1
    historic = basis.client.get(basis.path + f"/data?snapshot_id={first['id']}").json()
    assert next(r for r in historic["data"]["requirements"] if r["key"] == "a")["text"] == (
        "A标段质保三年"
    )
    assert corrected["id"] in {r["id"] for r in second["data"]["requirements"]}
    response = basis.client.post(basis.path + "/context", json={
        "snapshot_id": first["id"], "purpose": "outline",
        "lot_id": first["data"]["lots"][0]["lot_id"],
    })
    assert response.status_code == 409 and response.json()["error"]["code"] == "data_stale"
    other = analysis_api.start_analysis(
        basis.project_id, analysis_api.AnalysisInput(), basis.request
    )
    foreign = basis.client.get(
        f"/api/v1/analysis/reports/{other['id']}/data?snapshot_id={first['id']}",
    )
    assert foreign.status_code == 409
    assert basis.client.get("/api/v1/analysis/reports/999999/data").status_code == 404


def test_running_and_changed_report_cannot_supply_context(basis):
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    request = {"snapshot_id": snapshot["id"], "purpose": "outline",
               "lot_id": snapshot["data"]["lots"][0]["lot_id"]}
    basis.db.execute("UPDATE analysis_report SET status='pending' WHERE id=:id",
                     {"id": basis.report_id})
    response = basis.client.post(basis.path + "/context", json=request)
    assert response.status_code == 409 and response.json()["error"]["code"] == "report_running"
    basis.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id",
                     {"id": basis.report_id})
    analysis_api.save_settings(basis.project_id, analysis_api.AnalysisSettings(category="service"),
                            basis.request)
    response = basis.client.post(basis.path + "/context", json=request)
    assert response.status_code == 409 and response.json()["error"]["code"] == "data_stale"


@pytest.mark.parametrize("run_status", ["pending", "running"])
def test_canceled_retry_preserves_previous_formal_snapshot(basis, run_status):
    first = publish_data_snapshot(basis.db, basis.report_id)
    retried = basis.client.post(basis.path + "/retry", json={
        "module_keys": ["project_basic_info_parsing"],
    })
    assert retried.status_code == 202
    basis.db.execute("UPDATE agent_module_run SET status=:status WHERE module_id=:id",
                     {"status": run_status, "id": basis.module_id})
    # 模拟取消已落库、执行者仍在退出的窗口；无执行者的 HTTP 取消现会直接结束运行账。
    basis.db.execute("UPDATE analysis_report SET status='canceled' WHERE id=:id",
                     {"id": basis.report_id})
    assert publish_data_snapshot(basis.db, basis.report_id) is None
    request = {"snapshot_id": first["id"], "purpose": "outline",
               "lot_id": first["data"]["lots"][0]["lot_id"]}
    assert basis.client.get(basis.path + "/data").json()["stale"] is True
    assert basis.client.post(basis.path + "/context", json=request).status_code == 409

    # 最新运行已终止且正式投影未变，上一轮提交仍是当前版本。
    basis.db.execute("UPDATE agent_module_run SET status='canceled' WHERE module_id=:id",
                     {"id": basis.module_id})
    basis.db.execute("UPDATE analysis_module SET status='canceled' WHERE id=:id",
                     {"id": basis.module_id})
    assert basis.client.get(basis.path + "/data").json()["stale"] is False
    assert basis.client.post(basis.path + "/context", json=request).status_code == 200
    second = publish_data_snapshot(basis.db, basis.report_id)
    assert second["revision"] == first["revision"]
    assert second["data"] == first["data"]
    assert basis.client.get(basis.path + "/data").json()["stale"] is False
    assert basis.client.post(basis.path + "/context", json=request).status_code == 200


def test_superseded_pending_attempt_does_not_block_the_new_terminal_snapshot(basis):
    first = publish_data_snapshot(basis.db, basis.report_id)
    for _ in range(2):
        assert basis.client.post(basis.path + "/retry", json={
            "module_keys": ["project_basic_info_parsing"],
        }).status_code == 202
        basis.db.execute("UPDATE analysis_report SET status='canceled' WHERE id=:id",
                         {"id": basis.report_id})
    # 构造旧版本遗留的 pending attempt；新取消接口会清理，但历史记录仍须兼容读取。
    basis.db.execute("""UPDATE agent_module_run SET status='pending' WHERE module_id=:id
        AND attempt<(SELECT max(attempt) FROM agent_module_run WHERE module_id=:id)""",
        {"id": basis.module_id})
    basis.db.execute("""UPDATE agent_module_run SET status='canceled' WHERE module_id=:id
        AND attempt=(SELECT max(attempt) FROM agent_module_run WHERE module_id=:id)""",
        {"id": basis.module_id})
    basis.db.execute("UPDATE analysis_module SET status='canceled' WHERE id=:id",
                     {"id": basis.module_id})
    second = publish_data_snapshot(basis.db, basis.report_id)
    assert second["revision"] == first["revision"]
    assert basis.client.get(basis.path + "/data").json()["stale"] is False


@pytest.mark.parametrize("run_status", ["pending", "running"])
def test_cancel_orphaned_retry_keeps_previous_snapshot_without_drafts(basis, run_status):
    first = publish_data_snapshot(basis.db, basis.report_id)
    assert basis.client.post(basis.path + "/retry", json={
        "module_keys": ["project_basic_info_parsing"],
    }).status_code == 202
    basis.db.execute("UPDATE agent_module_run SET status=:status WHERE module_id=:id",
                     {"status": run_status, "id": basis.module_id})
    result = basis.client.post(basis.path + "/cancel")
    assert result.json() == {"status": "canceled", "canceling": False}
    current = basis.client.get(basis.path + "/data").json()
    assert current["revision"] == first["revision"]
    assert current["data"] == first["data"]
    assert basis.client.post(basis.path + "/context", json={
        "snapshot_id": first["id"], "purpose": "outline",
        "lot_id": first["data"]["lots"][0]["lot_id"],
    }).status_code == 200


def test_known_project_lots_missing_from_analysis_require_explicit_selection(basis):
    publish_data_snapshot(basis.db, basis.report_id)
    known = analysis_api.analysis_status(basis.project_id, basis.request)["lots"]
    basis.db.execute("UPDATE analysis_report SET lot_settings=CAST(:lots AS JSONB) WHERE id=:id",
                     {"lots": encode(known), "id": basis.report_id})
    business = copy.deepcopy(basis.business)
    business["records"] = [r for r in business["records"] if r["key"] != "lot-b"]
    basis.db.execute("UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
                     {"data": encode(business), "id": basis.module_id})
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    assert len(snapshot["data"]["lots"]) == 1
    assert any(g["code"] == "lot_catalog_unknown" for g in snapshot["data"]["gaps"])
    response = basis.client.post(basis.path + "/context", json={
        "snapshot_id": snapshot["id"], "purpose": "outline",
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "lot_scope_unresolved"


def test_revoked_source_used_only_in_gaps_is_redacted_without_rewriting_snapshot(basis):
    secret = "仅在已撤销附件中的待核对内容"
    add_source(basis.conn, basis.project_id, secret)
    sources = basis.db.sources(basis.db.collections_for_project(basis.project_id))
    revoked = next(s for s in sources if s["source_id"] != basis.source["source_id"])
    basis.db.execute(
        "UPDATE analysis_report SET source_snapshot=CAST(:sources AS JSONB) WHERE id=:id",
        {"sources": encode(sources), "id": basis.report_id},
    )
    business = copy.deepcopy(basis.business)
    business["gaps"] = [{"key": "missing", "topic": "other", "code": "unresolved_reference",
                         "detail": secret, "scope": COMMON}]
    basis.db.execute("UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
                     {"data": encode(business), "id": basis.module_id})
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    basis.db.execute("UPDATE project_file SET deleted_at=now() WHERE id=:id",
                     {"id": revoked["project_file_id"]})
    response = basis.client.get(basis.path + "/data")
    assert response.status_code == 200 and secret not in response.text
    assert response.json()["data"]["readiness"] == "unavailable"
    denied = basis.client.post(basis.path + "/context", json={
        "snapshot_id": snapshot["id"], "purpose": "outline",
        "lot_id": snapshot["data"]["lots"][0]["lot_id"],
    })
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "source_unavailable"
    persisted = basis.db.rows("SELECT data FROM analysis_data_snapshot WHERE id=:id",
                             {"id": snapshot["id"]})[0]["data"]
    assert secret in encode(persisted)


def test_content_references_and_revocation_during_retrieval(basis, monkeypatch):
    company = basis.client.post("/api/v1/knowledge/collections", json={
        "name": "企业证明", "purpose": "company",
    }).json()
    add_source(basis.conn, company["upload_project_id"], "企业已有类似业绩，仅作参考")
    linked = basis.client.put(f"/api/v1/projects/{basis.project_id}/knowledge/collections", json={
        "collection_ids": [company["id"]],
    })
    assert linked.status_code == 200
    sources = basis.db.sources([company["id"]])
    basis.db.execute(
        "UPDATE analysis_report SET reference_snapshot=CAST(:sources AS JSONB) WHERE id=:id",
        {"sources": encode(sources), "id": basis.report_id},
    )
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    reference = basis.db.readable_chunks(sources[0])[0]
    requirement = next(r for r in snapshot["data"]["requirements"] if r["key"] == "a")
    revoke = False

    async def retrieve(_db, selected, query, *_args, **_kwargs):
        assert {s["purpose"] for s in selected} == {"company"}
        assert query == requirement["text"]
        if revoke:
            basis.db.execute("UPDATE project_file SET deleted_at=now() WHERE id=:id",
                             {"id": basis.source["project_file_id"]})
        return [reference], {}

    monkeypatch.setattr(analysis, "retrieve_chunks", retrieve)
    request = {"snapshot_id": snapshot["id"], "purpose": "content",
               "lot_id": snapshot["data"]["lots"][0]["lot_id"],
               "requirement_ids": [requirement["id"]]}
    first = basis.client.post(basis.path + "/context", json=request)
    assert first.status_code == 200
    assert first.json()["references"][0]["purpose"] == "company"
    assert [r["id"] for r in first.json()["requirements"]] == [requirement["id"]]
    revoke = True
    denied = basis.client.post(basis.path + "/context", json=request)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "source_unavailable"
