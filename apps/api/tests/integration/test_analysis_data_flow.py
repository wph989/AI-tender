"""临时 PostgreSQL 表验证业务快照和 HTTP 取数，不调用供应商或改写业务数据。"""

import copy
import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from store import SqlStore
from test_knowledge_flow import add_source
from test_knowledge_flow import environment as environment

from tender.api.analysis import routes as analysis_api
from tender.api.knowledge import routes as knowledge
from tender.api.shared.errors import install_error_handlers
from tender.application.analysis import service as analysis
from tender.application.analysis.data import (
    BusinessRecord,
    module_data,
    prepare_records,
)
from tender.application.analysis.data_store import publish_data_snapshot
from tender.application.analysis.output import output_schema
from tender.application.analysis.runtime import limits_snapshot
from tender.application.knowledge.content import encode, source_signature

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
    store = knowledge.knowledge_service(request).store
    # 夹具与终态断言要写测试 schema：直连同一批临时表，但展示与发布仍走仓储。
    db = SqlStore(store.engine, store.company_id)
    source = db.sources(db.collections_for_project(pid))[0]
    block = db.readable_chunks(source)[0]

    def record(key, title, content, *, kind="requirement", lot=None, code=None):
        return BusinessRecord(
            key=key, title=title, text=content, kind=kind, code=code,
            group="分标信息" if kind == "lot" else "项目基本信息",
            content={"字段": title, "内容": content},
            scope={"kind": "lots", "lot_refs": [lot]} if lot else COMMON,
            structuring="complete",
            citations=[{"block_id": block["block_id"]}],
        )

    report = db.report(created["id"])
    state = {"output_schema": output_schema(report["skill_snapshot"], "project_basic_info_parsing")}
    state["quality_input_signature"] = source_signature(
        report["source_snapshot"] + report["reference_snapshot"]
    )
    items = prepare_records([
        record("lot-a", "A标段", "A标段", kind="lot", code="A"),
        record("lot-b", "B标段", "B标段", kind="lot", code="B"),
        record("common", "证明材料", "所有标段须提供营业执照"),
        record("a", "质保期", "A标段质保三年", lot="A"),
        record("b", "质保期", "B标段质保五年", lot="B"),
    ], state, {block["block_id"]: block}, "project_basic_info_parsing")
    for item in items:
        item["verification"] = "supported"
    state.update(staged_items=items, agent_workspace={
        "finalized": True, "final_ids": [item["id"] for item in items],
    })
    business = module_data(state)
    module_id = conn.execute(text("""INSERT INTO analysis_module
        (report_id,module_key,title,status,business_data)
        VALUES (:report,'project_basic_info_parsing','项目概况','completed',
                CAST(:business AS JSONB)) RETURNING id"""), {
            "report": created["id"],
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


def confirm_snapshot_records(basis, snapshot):
    loaded = basis.client.get(basis.path + f"/data?snapshot_id={snapshot['id']}").json()
    for bucket in ("lots", "facts", "requirements", "format_nodes", "relations"):
        for record in loaded["data"][bucket]:
            response = basis.client.post(basis.path + "/reviews", json={
                "snapshot_id": snapshot["id"], "record_id": record["id"],
                "previous_review_id": None, "decision": "confirmed", "note": "",
                "corrected_text": None,
            })
            assert response.status_code == 200, response.text


def test_lot_without_original_code_publishes_and_resolves_by_verified_name(basis):
    report = basis.db.report(basis.report_id)
    state = {"output_schema": output_schema(report["skill_snapshot"], "project_basic_info_parsing")}
    state["quality_input_signature"] = source_signature(
        report["source_snapshot"] + report["reference_snapshot"]
    )
    records = [
        BusinessRecord(
            key="named-lot", title="A标段", text="A标段", kind="lot", scope=COMMON,
            group="分标信息", content={"字段": "A标段", "内容": "A标段"},
            citations=[{"block_id": basis.block["block_id"]}],
        ),
        BusinessRecord(
            key="warranty", title="质保要求", text="A标段质保三年", kind="requirement",
            group="项目基本信息", content={"字段": "质保要求", "内容": "A标段质保三年"},
            scope={"kind": "lots", "lot_refs": ["A标段"]}, structuring="complete",
            citations=[{"block_id": basis.block["block_id"]}],
        ),
    ]
    items = prepare_records(records, state, {basis.block["block_id"]: basis.block},
                            "project_basic_info_parsing")
    for item in items:
        item["verification"] = "supported"
    state["agent_workspace"] = {"finalized": True, "final_ids": [i["id"] for i in items]}
    state["staged_items"] = items
    basis.db.execute(
        "UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
        {"data": encode(module_data(state)), "id": basis.module_id},
    )
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    confirm_snapshot_records(basis, snapshot)
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
    # 服务端按实际已读块生成原文范围，核对持久化引用身份。
    assert refs[0]["quote"] == basis.block["content"]
    assert refs[0]["element_id"] == basis.block["element_id"]
    # 独立数据入口同样检查实时依据，删除来源后不能绕过报告权限读取正文。
    basis.db.execute("DELETE FROM knowledge_source WHERE id=:id", {"id": basis.source["source_id"]})
    hidden = basis.client.get(path).json()
    assert hidden["records"] == [] and hidden["evidence"] == {}
    assert basis.client.get(basis.path + "/modules/unknown/records").status_code == 404


def test_module_records_query_loads_one_topic_and_keeps_company_isolation(basis):
    basis.db.execute("""INSERT INTO analysis_module
        (report_id,module_key,title,status,business_data)
        VALUES (:report,'tech_requirement_parsing','技术要求','completed',
                CAST(:data AS JSONB))""", {
        "report": basis.report_id,
        "data": encode({"records": [], "evidence": {}, "research_summary": "其它专题"}),
    })
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("SELECT analysis_module."):
            statements.append(statement)

    # 捕获真实SQL，避免夹具用全报告过滤来掩盖仓储的单专题取数退化。
    event.listen(basis.conn, "before_cursor_execute", capture)
    try:
        response = basis.client.get(
            basis.path + "/modules/project_basic_info_parsing/records",
        )
    finally:
        event.remove(basis.conn, "before_cursor_execute", capture)
    assert response.status_code == 200 and len(response.json()["records"]) == 5
    assert len(statements) == 1
    assert "analysis_module.module_key =" in statements[0]
    assert "analysis_module.report_id =" in statements[0]
    assert "analysis_report.company_id =" in statements[0]
    assert basis.db.report_module(basis.report_id, "missing") is None
    assert SqlStore(basis.db.engine, 2).report_module(
        basis.report_id, "project_basic_info_parsing",
    ) is None
    assert basis.client.get(basis.path + "/modules/missing/records").status_code == 404


def test_display_queries_keep_protocol_and_schema_without_loading_private_rules(basis):
    key = "project_basic_info_parsing"
    full = basis.db.report(basis.report_id)
    overview = basis.db.report_view(basis.report_id)
    view = basis.db.report_view(basis.report_id, [key])
    assert overview["skill_snapshot"] == {
        analysis.FLOW_VERSION_KEY: full["skill_snapshot"][analysis.FLOW_VERSION_KEY],
    }
    assert output_schema(view["skill_snapshot"], key) == output_schema(full["skill_snapshot"], key)
    assert len(view["skill_snapshot"]) == 2
    assert basis.db.report(basis.report_id) == full
    summary = basis.db.report_module_summaries(basis.report_id)[0]
    assert summary["id"] == basis.module_id
    assert "records" not in summary["business_data"] and "evidence" not in summary["business_data"]
    assert summary["business_data"]["quality_input_signature"] == basis.business[
        "quality_input_signature"
    ]
    other_company = SqlStore(basis.db.engine, 2)
    assert other_company.report_view(basis.report_id, [key]) is None
    assert other_company.report_module_summaries(basis.report_id) == []


def test_batch_record_refresh_reuses_only_current_visible_content(basis):
    key = "project_basic_info_parsing"
    path = basis.path + "/records"
    payload = {"module_keys": [key], "versions": {}}
    first = basis.client.post(path, json=payload)
    assert first.status_code == 200, first.text
    update = first.json()["modules"][0]
    assert update["data"] == basis.client.get(basis.path + f"/modules/{key}/records").json()
    payload["versions"][key] = update["version"]
    assert basis.client.post(path, json=payload).json()["modules"] == [
        {"module_key": key, "version": update["version"]},
    ]
    # 有旧版本也必须重新核验；原文撤销后返回新的空正文供页面清除缓存。
    basis.db.execute("DELETE FROM knowledge_source WHERE id=:id", {"id": basis.source["source_id"]})
    hidden = basis.client.post(path, json=payload).json()["modules"][0]
    assert hidden["version"] != update["version"]
    assert hidden["data"]["records"] == [] and hidden["data"]["evidence"] == {}


def test_batch_refresh_isolates_missing_topic_and_limits_request_size(basis):
    key = "project_basic_info_parsing"
    path = basis.path + "/records"
    response = basis.client.post(path, json={"module_keys": [key, "missing"], "versions": {}})
    assert response.status_code == 200, response.text
    updates = response.json()["modules"]
    assert len(updates[0]["data"]["records"]) == 5
    assert updates[1] == {"module_key": "missing", "error": "分析维度不存在"}
    assert basis.client.post(path, json={"module_keys": [key] * 14}).status_code == 400
    invalid = basis.client.post(path, json={"module_keys": [key], "versions": {key: "bad"}})
    assert invalid.status_code == 400
    assert basis.client.post(basis.path.replace(str(basis.report_id), "999999") + "/records",
                             json={"module_keys": [key]}).status_code == 404


@pytest.mark.parametrize("prefix", ["x" * 64, "甲" * 22])
def test_long_unknown_keys_return_topic_errors_without_sql_identifier_collision(basis, prefix):
    key = "project_basic_info_parsing"
    unknown = [prefix + "a", prefix + "b"]
    response = basis.client.post(basis.path + "/records", json={"module_keys": [key, *unknown]})
    assert response.status_code == 200, response.text
    updates = response.json()["modules"]
    assert len(updates[0]["data"]["records"]) == 5
    assert updates[1:] == [
        {"module_key": module_key, "error": "分析维度不存在"} for module_key in unknown
    ]
    assert basis.client.get(basis.path + f"/modules/{unknown[0]}/records").status_code == 404


def test_partial_batch_filters_modules_in_sql_and_preserves_full_read(basis):
    key = "project_basic_info_parsing"
    for module_key in analysis.MODULES:
        if module_key != key:
            basis.db.execute("""INSERT INTO analysis_module
                (report_id,module_key,title,status,business_data)
                VALUES (:id,:key,:key,'completed',CAST(:data AS JSONB))""", {
                "id": basis.report_id, "key": module_key, "data": encode(basis.business),
            })
    assert len(basis.db.report_modules(basis.report_id)) == 13
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("SELECT analysis_module."):
            statements.append(statement)

    event.listen(basis.conn, "before_cursor_execute", capture)
    try:
        selected = basis.db.report_modules(basis.report_id, [key])
        assert [module["module_key"] for module in selected] == [key]
        assert len(statements) == 1 and "analysis_module.module_key IN" in statements[0]
        statements.clear()
        assert basis.db.report_modules(basis.report_id, []) == []
        assert statements == []
        response = basis.client.post(basis.path + "/records", json={"module_keys": [key]})
        assert response.status_code == 200, response.text
        assert len(response.json()["modules"]) == 1
        assert len(statements) == 1 and "analysis_module.module_key IN" in statements[0]
    finally:
        event.remove(basis.conn, "before_cursor_execute", capture)
    assert SqlStore(basis.db.engine, 2).report_modules(basis.report_id, [key]) == []
    assert SqlStore(basis.db.engine, 2).report_modules(basis.report_id) == []


def test_latest_snapshot_check_reads_only_id_and_detects_new_revision(basis):
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("SELECT analysis_data_snapshot.id"):
            statements.append(statement)

    event.listen(basis.conn, "before_cursor_execute", capture)
    try:
        assert basis.db.latest_snapshot_id(basis.report_id) == snapshot["id"]
    finally:
        event.remove(basis.conn, "before_cursor_execute", capture)
    assert len(statements) == 1
    assert "analysis_data_snapshot.data" not in statements[0]
    assert "analysis_data_snapshot.input_snapshot" not in statements[0]
    assert SqlStore(basis.db.engine, 2).latest_snapshot_id(basis.report_id) is None
    changed = copy.deepcopy(basis.business)
    changed["research_summary"] = "本轮新增核对结果"
    basis.db.execute("UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id", {
        "id": basis.module_id, "data": encode(changed),
    })
    newer = publish_data_snapshot(basis.db, basis.report_id)
    assert newer["id"] != snapshot["id"]
    assert basis.db.latest_snapshot_id(basis.report_id) == newer["id"]
    historical = basis.client.get(basis.path + f"/data?snapshot_id={snapshot['id']}")
    assert historical.status_code == 200, historical.text
    assert historical.json()["stale"]


def test_terminal_snapshot_is_idempotent_and_context_is_single_lot(basis):
    assert basis.client.get(basis.path + "/data").status_code == 409
    basis.db.execute("UPDATE analysis_report SET status='running' WHERE id=:id",
                     {"id": basis.report_id})
    assert publish_data_snapshot(basis.db, basis.report_id) is None
    basis.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id",
                     {"id": basis.report_id})
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    assert publish_data_snapshot(basis.db, basis.report_id)["id"] == snapshot["id"]
    confirm_snapshot_records(basis, snapshot)
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
        basis.db.execute(
            "UPDATE analysis_module SET status='partial',business_data='{}' WHERE id=:id",
            {"id": basis.module_id},
        )
        basis.conn.execute(text("""INSERT INTO agent_module_run
            (module_id,company_id,attempt,thread_id,status,limits,state)
            VALUES (:module,1,1,'business-stage','failed',CAST(:limits AS JSONB),
                    CAST(:state AS JSONB))"""), {
                "module": basis.module_id, "state": encode(basis.state),
                "limits": encode(limits_snapshot(basis.db)),
            })
    module = basis.client.get(basis.path).json()["modules"][0]
    assert "items" not in module and "business_data" not in module
    result = basis.client.get(basis.path + "/modules/project_basic_info_parsing/records").json()
    items = result["records"]
    if staged:
        assert not items
        return
    assert len([item for item in items if item["title"] == "质保期"]) == 2
    assert {item["id"] for item in items} == {r["id"] for r in basis.business["records"]}
    assert "business_data" not in module
    assert all("business" not in item for item in items)


def test_new_revision_preserves_history_and_rejects_old_or_foreign_snapshot(basis):
    first = publish_data_snapshot(basis.db, basis.report_id)
    business = copy.deepcopy(basis.business)
    corrected = next(r for r in business["records"] if r["key"] == "a")
    corrected["content"]["内容"] = "A标段质保四年"
    corrected["text"] = "字段：质保期\n内容：A标段质保四年"
    business["evidence"][corrected["evidence_ids"][0]]["quote"] = "A标段质保四年"
    basis.db.execute("UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
                     {"data": encode(business), "id": basis.module_id})
    second = publish_data_snapshot(basis.db, basis.report_id)
    assert second["revision"] == first["revision"] + 1
    historic = basis.client.get(basis.path + f"/data?snapshot_id={first['id']}").json()
    assert next(r for r in historic["data"]["requirements"] if r["key"] == "a")["text"] == (
        "字段：质保期\n内容：A标段质保三年"
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
    confirm_snapshot_records(basis, first)
    retried = basis.client.post(basis.path + "/retry", json={
        "module_keys": ["project_basic_info_parsing"],
    })
    assert retried.status_code == 202
    basis.db.execute("UPDATE agent_module_run SET status=:status WHERE module_id=:id",
                     {"status": run_status, "id": basis.module_id})
    # 该用例没有持有执行锁，收尾会回收孤儿运行并继续使用上一版正式成果。
    basis.db.execute("UPDATE analysis_report SET status='canceled' WHERE id=:id",
                     {"id": basis.report_id})
    second = publish_data_snapshot(basis.db, basis.report_id)
    assert second["id"] == first["id"]
    assert second["revision"] == first["revision"]
    assert basis.client.get(basis.path + "/data").json()["stale"] is False
    request = {"snapshot_id": first["id"], "purpose": "outline",
               "lot_id": first["data"]["lots"][0]["lot_id"]}
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
    confirm_snapshot_records(basis, first)
    assert basis.client.post(basis.path + "/retry", json={
        "module_keys": ["project_basic_info_parsing"],
    }).status_code == 202
    basis.db.execute("UPDATE agent_module_run SET status=:status WHERE module_id=:id",
                     {"status": run_status, "id": basis.module_id})
    result = basis.client.post(basis.path + "/cancel")
    assert result.json() == {"status": "canceled", "canceling": False}
    current = basis.client.get(basis.path + "/data").json()
    assert current["revision"] == first["revision"]
    assert {record["human_review_status"] for key in (
        "lots", "facts", "requirements", "format_nodes", "relations",
    ) for record in current["data"][key]} == {"confirmed"}
    assert {key: len(current["data"][key]) for key in first["data"]
            if key in {"lots", "facts", "requirements", "format_nodes", "relations"}} == {
        key: len(first["data"][key])
        for key in first["data"]
        if key in {"lots", "facts", "requirements", "format_nodes", "relations"}
    }
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


def test_snapshot_review_resolves_evidence_in_same_transaction(basis):
    report = basis.db.report(basis.report_id)
    signature = source_signature(report["source_snapshot"] + report["reference_snapshot"])
    business = copy.deepcopy(basis.business)
    business["quality_input_signature"] = signature
    basis.db.execute("UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
                     {"data": encode(business), "id": basis.module_id})
    snapshot = publish_data_snapshot(basis.db, basis.report_id)

    loaded = basis.client.get(basis.path + "/data").json()
    assert loaded["stale"] is False
    requirement = loaded["data"]["requirements"][0]
    assert requirement["human_review_status"] == "pending"

    service = analysis_api.analysis_service(basis.request)
    repository = service.store
    original_transaction = repository.transaction
    original_resolve = repository.resolve
    active = {"transaction": None}

    @contextmanager
    def tracked_transaction():
        with original_transaction() as tx:
            active["transaction"] = tx
            try:
                yield tx
            finally:
                active["transaction"] = None

    def tracked_resolve(ref, **kwargs):
        if active["transaction"] is not None:
            assert kwargs.get("bound") is active["transaction"]._connection()
        return original_resolve(ref, **kwargs)

    repository.transaction = tracked_transaction
    repository.resolve = tracked_resolve
    result = service.record_human_review(
        basis.report_id,
        analysis.RecordReviewInput(
            snapshot_id=snapshot["id"], record_id=requirement["id"],
            previous_review_id=None, decision="confirmed",
        ),
        actor="reviewer",
    )
    assert result["decision"] == "confirmed"
    updated = basis.client.get(basis.path + "/data").json()
    reviewed = next(r for r in updated["data"]["requirements"] if r["id"] == requirement["id"])
    assert reviewed["human_review_status"] == "confirmed"


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
    business = copy.deepcopy(basis.business)
    business["quality_input_signature"] = source_signature(
        basis.db.report(basis.report_id)["source_snapshot"] + sources
    )
    basis.db.execute("UPDATE analysis_module SET business_data=CAST(:data AS JSONB) WHERE id=:id",
                     {"data": encode(business), "id": basis.module_id})
    snapshot = publish_data_snapshot(basis.db, basis.report_id)
    confirm_snapshot_records(basis, snapshot)
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
