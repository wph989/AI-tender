"""真实 PostgreSQL 临时表验证索引、检索、问答与报告展示；解析链路由 DeepAgents 专项用例覆盖。"""

import asyncio
import json
import os
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from data_schema import install_data_schema
from http_client import api_request
from langchain_core.messages import AIMessage, message_to_dict
from sqlalchemy import create_engine, text

from tender.adapters.pg.repositories.analysis.runtime import AgentRunStore
from tender.adapters.pg.repositories.knowledge.store import KnowledgeStore, sync_sources
from tender.api.analysis import routes as analysis_api
from tender.api.knowledge import routes as knowledge
from tender.api.projects import routes as projects
from tender.application.analysis.data_store import publish_data_snapshot
from tender.application.analysis.drafts import DraftWorkspace
from tender.application.analysis.execution import prepare_report
from tender.application.analysis.runtime import AgentRuntime
from tender.application.knowledge import execution as knowledge_execution
from tender.application.knowledge.content import source_signature, validate_items
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.config.registry import ConfigRegistry
from tender.core import di, settings
from tender.ports.llm.chat import Completion
from tender.worker.knowledge import tasks as worker

pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证"
)


@pytest.fixture
def environment(monkeypatch):
    # 本文件聚焦索引、检索、问答与报告展示；DeepAgents 并发与恢复场景有独立集成用例。
    db = create_engine(settings.database_url())
    with db.connect() as connection, connection.begin() as transaction:
        tables = (
            "project",
            "document",
            "document_version",
            "parse_run",
            "page",
            "element",
            "project_file",
            "lot",
            "job",
            "knowledge_collection",
            "knowledge_source",
            "project_knowledge_collection",
            "knowledge_index",
            "knowledge_chunk",
            "analysis_report",
            "analysis_module",
            # 运行行必须与临时模块表一起隔离，不能引用真实库里碰巧同 ID 的历史模块。
            "agent_module_run",
            "knowledge_answer",
            "llm_feature_model",
            "llm_model",
            "llm_provider",
        )
        for table in tables:
            connection.execute(
                text(f"""CREATE TEMP TABLE {table}
                (LIKE public.{table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)
                ON COMMIT DROP""")
            )
            if table not in {"job", "project_knowledge_collection"}:
                connection.execute(text(f"CREATE TEMP SEQUENCE test_{table}_id_seq"))
                connection.execute(
                    text(
                        f"ALTER TABLE {table} ALTER COLUMN id "
                        f"SET DEFAULT nextval('test_{table}_id_seq')"
                    )
                )
        install_data_schema(connection, temporary=True)
        facade = SimpleNamespace(
            connect=lambda: nullcontext(connection), begin=lambda: nullcontext(connection)
        )
        request = SimpleNamespace(
            # 与正式装配一样提供配置端口；不能让用例为了不完整夹具自行创建数据库实现。
            app=SimpleNamespace(state=SimpleNamespace(components=SimpleNamespace(
                engine=facade, configs=ConfigRegistry(facade),
            ))),
            headers={},
        )
        monkeypatch.setattr(settings, "company_id", lambda: 1)
        monkeypatch.setattr(worker, "_store", lambda: KnowledgeStore(facade, 1))
        def executor(db):
            result = di.create_knowledge_executor(db)
            result.model_factory = lambda *args, **limits: FixtureModel()
            return result

        monkeypatch.setattr(worker, "create_knowledge_executor", executor)
        project = projects.create_project(projects.ProjectCreate(name="综合分析专项"), request)
        yield request, connection, project["id"]
        transaction.rollback()
    db.dispose()


def add_source(connection, pid, content, status="completed"):
    doc = connection.execute(
        text("INSERT INTO document (title,company_id) VALUES ('样本',1) RETURNING id")
    ).scalar_one()
    version = connection.execute(
        text("""INSERT INTO document_version
        (document_id,version_no,sha256,mime,size_bytes,original_key,pdf_key,pdf_sha256,is_converted,page_count)
        VALUES (:doc,1,:sha,'application/pdf',100,'test.pdf','test.pdf',:sha,false,1)
        RETURNING id"""),
        {"doc": doc, "sha": f"{doc:064x}"},
    ).scalar_one()
    connection.execute(
        text("""INSERT INTO project_file
        (project_id,version_id,role,display_name,is_parseable,sort_no,sha256)
        VALUES (:pid,:version,'main',:name,true,:sort,:sha)"""),
        {
            "pid": pid,
            "version": version,
            "name": f"材料{doc}.pdf",
            "sort": doc,
            "sha": f"{doc:064x}",
        },
    )
    run = connection.execute(
        text("""INSERT INTO parse_run
        (version_id,provider_version,tier,schema_version,status,page_count)
        VALUES (:version,'test','standard','1',:status,1) RETURNING id"""),
        {"version": version, "status": status},
    ).scalar_one()
    connection.execute(
        text("""INSERT INTO element
        (version_id,run_id,page_no,order_no,anchor,type,text,bbox_x0,bbox_y0,bbox_x1,bbox_y1)
        VALUES (:version,:run,1,1,'p1b1','text',:content,0.1,0.1,0.8,0.2)"""),
        {"version": version, "run": run, "content": content},
    )
    sync_sources(connection, pid)
    return version, run


class FixtureModel:
    """问答链路用可控适配器：以原生工具动作驱动独立问答 Agent，并应答支持性校验。"""

    def __init__(self):
        self.rounds = 0

    async def complete(self, prompt):
        # 支持性校验：待审字段逐项返回“无未支持断言”。
        items = json.loads(prompt.rsplit("\n", 1)[1])
        return Completion(
            json.dumps({"reviews": [{"unsupported_claims": [], "supported": True} for _ in items]}),
            "fixture",
        )

    async def chat(self, messages, tools):
        self.rounds += 1
        if self.rounds == 1:
            call = {
                "name": "search_document",
                "args": {"query": "资质"},
                "id": "qa_call_1",
                "type": "tool_call",
            }
        else:
            blocks = []
            for message in messages:
                data = message.get("data", {})
                if message.get("type") == "tool" and data.get("name") == "search_document":
                    blocks = json.loads(data["content"]).get("blocks", [])
            call = {
                "name": "submit_analysis",
                "args": {
                    "fields": [
                        {
                            "field": block.get("chapter") or "原文要点",
                            "group": "",
                            "sort_order": index,
                            "values": [
                                {
                                    "value": block["content"],
                                    "citations": [
                                        {"block_id": block["block_id"], "quote": block["content"]}
                                    ],
                                }
                            ],
                            "note": "",
                        }
                        for index, block in enumerate(blocks)
                    ],
                    "relations": [],
                    "research_summary": "已检索并核对原文",
                    "final": True,
                },
                "id": "qa_call_2",
                "type": "tool_call",
            }
        return Completion(
            content="",
            model="fixture",
            agent_message=message_to_dict(AIMessage(content="", tool_calls=[call])),
        )

    async def aclose(self):
        pass


def configure(request, pid):
    analysis_api.save_settings(pid, analysis_api.AnalysisSettings(category="engineering"), request)


def publish_relation(request, conn, report_id, blocks):
    """走真实草稿、自查和发布入口，避免旧表夹具掩盖生产关系链路断开。"""
    store = knowledge.knowledge_service(request).store
    report = store.report(report_id)
    key = "project_basic_info_parsing"
    state = {
        "output_schema": {"version": "1", "sections": [{
            "title": "项目要求", "layout": "table", "columns": ["字段", "内容"],
            "title_column": "字段",
        }]},
        "quality_input_signature": source_signature(
            report["source_snapshot"] + report["reference_snapshot"]
        ),
    }
    book = DraftWorkspace(state, {block["block_id"]: block for block in blocks}, key)
    rows = []
    for index, title in enumerate(("甲级资质", "履约保函")):
        block = blocks[min(index, len(blocks) - 1)]
        rows.append({
            "key": f"node-{index}", "kind": "requirement", "group": "项目要求",
            "content": {"字段": title, "内容": block["content"]},
            "scope": {"kind": "common"}, "block_ids": [block["block_id"]],
        })
    rows.append({
        "key": "link", "kind": "relation", "group": "项目要求", "predicate": "requires",
        "subject_key": "node-0", "object_key": "node-1",
        "content": {"字段": "依赖", "内容": "甲级资质要求关联履约保函提交要求"},
        "scope": {"kind": "common"}, "block_ids": [block["block_id"] for block in blocks],
    })
    saved = book.save_records(rows, "draft-1")
    assert saved["rejected"] == [], saved
    receipts = saved["accepted"]
    book.record_review([{
        "record_id": row["id"], "version": row["version"], "status": "passed",
        "reason": "已对照全部项目原文核对依赖关系与共同适用范围",
        "block_ids": [block["block_id"] for block in blocks],
    } for row in receipts], [], "review-1")
    assert store.relation_snapshot(report["project_id"]) is None
    book.finalize([row["id"] for row in receipts], "已核对项目要求及其依赖关系")
    module_id = conn.execute(text("""INSERT INTO analysis_module
        (report_id,module_key,title,status) VALUES (:report,:key,'项目概况','completed')
        RETURNING id"""), {"report": report_id, "key": key}).scalar_one()
    # 夹具共用事务连接，无需创建配额锁引擎；正式成果仍由运行仓储的原发布方法落库。
    runtime_store = object.__new__(AgentRunStore)
    runtime_store.run = {"module_id": module_id}
    runtime_store._publish(conn, AgentRuntime._draft_payload(state["draft"]))
    conn.execute(text("UPDATE analysis_report SET status='completed' WHERE id=:id"),
                 {"id": report_id})
    snapshot = publish_data_snapshot(store, report_id)
    assert len(snapshot["data"]["relations"]) == 1
    return snapshot


def test_retired_report_is_hidden_from_application_but_history_is_preserved(environment):
    """退役协议不再进入应用展示，数据库中的原报告与记录仍保留。"""
    request, conn, pid = environment
    version, run = add_source(conn, pid, "要求甲级资质。")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    conn.execute(
        text("UPDATE analysis_report SET runtime_version='legacy' WHERE id=:id"),
        {"id": report["id"]},
    )
    assert version and run
    status = analysis_api.analysis_status(pid, request)
    assert all(item["id"] != report["id"] for item in status["reports"])
    exc = api_request(
        request,
        analysis_api.router,
        'GET',
        f"/api/v1/analysis/reports/{report['id']}",
    )
    assert exc.status_code >= 400
    assert exc.status_code == 409 and exc.json()["error"]["code"] == "runtime_retired"
    stored = conn.execute(
        text("SELECT id, runtime_version FROM analysis_report WHERE id=:id"),
        {"id": report["id"]},
    ).mappings().one()
    assert stored["runtime_version"] == "legacy"


def test_unfinished_module_does_not_show_saved_drafts(environment):
    """暂存结果只在工作区，报告详情只展示正式结果。"""
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    store = KnowledgeStore(request.app.state.components.engine, 1)
    collection = knowledge.project_knowledge(pid, request)["collection_id"]
    block = store.readable_chunks(store.sources([collection])[0])[0]
    item = validate_items(
        [
            {
                "field": "资质",
                "group": "",
                "sort_order": 0,
                "values": [
                    {
                        "value": block["content"],
                        "citations": [{"block_id": block["block_id"], "quote": block["content"]}],
                    }
                ],
                "note": "",
            }
        ],
        {block["block_id"]: block},
    )[0]
    item["verification"] = "supported"
    module_id = conn.execute(
        text("""INSERT INTO analysis_module (report_id,module_key,title,status)
        VALUES (:report,'project_basic_info_parsing','项目概况','running')
        RETURNING id"""),
        {"report": report["id"]},
    ).scalar_one()
    conn.execute(
        text("""INSERT INTO agent_module_run
        (module_id,company_id,attempt,thread_id,status,limits,state)
        VALUES (:module,1,1,:thread,'failed','{}'::jsonb,CAST(:state AS JSONB))"""),
        {
            "module": module_id,
            "thread": f"analysis:{report['id']}:{module_id}:1",
            "state": json.dumps(
                {"agent_workspace": {"finalized": False, "final_ids": []},
                 "staged_items": [item]}, ensure_ascii=False
            ),
        },
    )
    module = next(
        entry
        for entry in analysis_api.get_report(report["id"], request)["modules"]
        if entry["id"] == module_id
    )
    assert module["status"] == "running"
    assert "items" not in module
    records = analysis_api.get_module_records(
        report["id"], "project_basic_info_parsing", request
    )["records"]
    assert records == []


def test_retired_runtime_report_cannot_run_or_retry(environment):
    """Worker 拒绝运行退役报告，读取与补跑接口均返回明确错误。"""
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    conn.execute(
        text("UPDATE analysis_report SET runtime_version='legacy' WHERE id=:id"),
        {"id": report["id"]},
    )
    asyncio.run(worker._analyze_project(report["id"]))
    stored = conn.execute(
        text("SELECT status FROM analysis_report WHERE id=:id"), {"id": report["id"]}
    ).scalar_one()
    assert stored == "waiting"
    read_error = api_request(
        request,
        analysis_api.router,
        'GET',
        f"/api/v1/analysis/reports/{report['id']}",
    )
    assert read_error.status_code >= 400
    assert read_error.status_code == 409 and read_error.json()["error"]["code"] == "runtime_retired"
    exc = api_request(
        request,
        analysis_api.router,
        'POST',
        f"/api/v1/analysis/reports/{report['id']}/retry",
        payload=analysis_api.RetryInput(),
    )
    assert exc.status_code >= 400
    assert exc.status_code == 409 and exc.json()["error"]["code"] == "runtime_retired"


def test_reference_snapshot_change_marks_current_runtime_reports_stale(environment):
    """当前运行时记录参考来源快照，变化后报告标为过期。"""
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    # 另一项目的历史资料以参考库方式关联进来：当前运行时的报告未记录该来源，应判为已变化。
    reference = projects.create_project(projects.ProjectCreate(name="参考专项"), request)
    add_source(conn, reference["id"], "历史质保五年。")
    collection = conn.execute(
        text("""UPDATE knowledge_collection SET is_project=false,purpose='reference'
        WHERE upload_project_id=:id RETURNING id"""),
        {"id": reference["id"]},
    ).scalar_one()
    conn.execute(
        text("INSERT INTO project_knowledge_collection VALUES (:pid,:cid)"),
        {"pid": pid, "cid": collection},
    )
    assert analysis_api.get_report(report["id"], request)["stale"] is True
    conn.execute(
        text("UPDATE analysis_report SET runtime_version='legacy' WHERE id=:id"),
        {"id": report["id"]},
    )
    exc = api_request(
        request,
        analysis_api.router,
        'GET',
        f"/api/v1/analysis/reports/{report['id']}",
    )
    assert exc.status_code >= 400
    assert exc.json()["error"]["code"] == "runtime_retired"


def test_wait_for_missing_sources_or_explicit_partial_analysis(environment):
    """深运行时的准备阶段：资料不完整且未勾选部分分析时中止，勾选后只固定可用批次。"""
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    add_source(conn, pid, "未完成解析的资质要求。", status="failed")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    with pytest.raises(ValueError, match="未完整解析"):
        prepare_report(
            worker._store(), analysis_api.analysis_service(request).report_row(report["id"])
        )
    analysis_api.cancel_report(report["id"], request)
    partial = analysis_api.start_analysis(
        pid, analysis_api.AnalysisInput(allow_partial=True), request
    )
    fixed, sources = prepare_report(
        worker._store(), analysis_api.analysis_service(request).report_row(partial["id"])
    )
    assert fixed["coverage"]["partial"] is True
    assert [source["file_name"] for source in sources] == ["材料1.pdf"]
    assert analysis_api.get_report(partial["id"], request)["status"] == "running"


def test_graph_expansion_rejects_old_parse_evidence(environment):
    request, conn, pid = environment
    add_source(conn, pid, "甲级资质应提供证书。")
    configure(request, pid)
    store = KnowledgeStore(request.app.state.components.engine, 1)
    collection = knowledge.project_knowledge(pid, request)["collection_id"]
    sources = store.sources([collection])
    block = store.readable_chunks(sources[0])[0]
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    publish_relation(request, conn, report["id"], [block])
    _, relations = knowledge_execution.graph_expand(store, pid, [block], sources)
    assert len(relations) == 1
    changed_sources = [sources[0] | {"parse_run_id": sources[0]["parse_run_id"] + 1}]
    _, relations = knowledge_execution.graph_expand(store, pid, [block], changed_sources)
    assert not relations


@pytest.mark.parametrize("change", ["pending", "new_report", "deleted_project", "company"])
def test_graph_snapshot_requires_current_published_and_accessible_report(environment, change):
    request, conn, pid = environment
    add_source(conn, pid, "甲级资质应提供证书。")
    configure(request, pid)
    store = worker._store()
    sources = store.sources(store.collections_for_project(pid))
    blocks = store.readable_chunks(sources[0])
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    snapshot = publish_relation(request, conn, report["id"], blocks)
    assert store.relation_snapshot(pid)["id"] == snapshot["id"]
    if change == "pending":
        conn.execute(text("UPDATE analysis_report SET snapshot_pending=true WHERE id=:id"),
                     {"id": report["id"]})
    elif change == "new_report":
        latest = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
        conn.execute(text("UPDATE analysis_report SET status='completed' WHERE id=:id"),
                     {"id": latest["id"]})
    elif change == "deleted_project":
        conn.execute(text("UPDATE project SET deleted_at=now() WHERE id=:id"), {"id": pid})
    else:
        store = KnowledgeStore(store.engine, 2)
    assert store.relation_snapshot(pid) is None
    hits, relations = knowledge_execution.graph_expand(store, pid, [blocks[0]], sources)
    assert hits == [blocks[0]] and relations == []


def test_collections_isolate_retrieval_and_answers(environment):
    request, conn, pid = environment
    add_source(conn, pid, "本项目要求甲级资质。")
    library = knowledge.create_collection(
        knowledge.CollectionInput(name="历史标书", purpose="history"), request
    )
    add_source(conn, library["upload_project_id"], "旧项目要求乙级资质。")
    own_id = knowledge.project_knowledge(pid, request)["collection_id"]
    hits = asyncio.run(knowledge.search_collection(own_id, request, "资质"))["items"]
    assert len(hits) == 1 and "本项目" in hits[0]["content"]
    exc = api_request(
        request,
        knowledge.router,
        'POST',
        f"/api/v1/projects/{pid}/knowledge/ask",
        payload=knowledge.AskInput(question='资质', collection_ids=[library['id']]),
    )
    assert exc.status_code >= 400
    assert exc.status_code == 403
    question = knowledge.ask_project(pid, knowledge.AskInput(question="资质"), request)
    asyncio.run(worker._answer_question(question["id"]))
    answer = knowledge.get_answer(question["id"], request)
    assert answer["status"] == "completed"
    assert all(
        ref["collection_id"] == own_id
        for item in answer["items"]
        for value in item["values"]
        for ref in value["citations"]
    )


def test_question_agent_reads_graph_only_evidence(environment, monkeypatch):
    request, conn, pid = environment
    add_source(conn, pid, "本项目要求甲级资质。")
    add_source(conn, pid, "履约保函应在签约前提交。")
    configure(request, pid)
    store = worker._store()
    own_id = knowledge.project_knowledge(pid, request)["collection_id"]
    sources = store.sources([own_id])
    blocks = [row for source in sources for row in store.readable_chunks(source)]
    direct = next(row for row in blocks if "甲级资质" in row["content"])
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    publish_relation(request, conn, report["id"], blocks)

    async def retrieve_direct(*args, **kwargs):
        # 普通检索只命中资质，保函只能通过数据库图谱扩展进入 Agent 的工具结果。
        return [direct], {"mode": "keyword"}

    monkeypatch.setattr(knowledge_execution, "retrieve_chunks", retrieve_direct)
    question = knowledge.ask_project(pid, knowledge.AskInput(question="资质"), request)
    asyncio.run(worker._answer_question(question["id"]))
    answer = knowledge.get_answer(question["id"], request)
    assert answer["status"] == "completed", answer["error_message"]
    assert any("履约保函" in value["value"] for item in answer["items"] for value in item["values"])
    assert answer["snapshot"]["retrieved_blocks"] == 2
    assert answer["snapshot"]["graph_used"] is True
    assert answer["snapshot"]["graph_relation_count"] == 1


def test_index_without_embedding_retains_full_text(environment):
    request, conn, pid = environment
    add_source(conn, pid, "资质要求。" * 600)
    collection = knowledge.project_knowledge(pid, request)["collection_id"]
    knowledge.reindex_collection(collection, request)
    index_id = conn.execute(text("SELECT id FROM knowledge_index")).scalar_one()
    asyncio.run(worker._build_index(index_id))
    row = (
        conn.execute(text("SELECT status,embedding_model_id FROM knowledge_index")).mappings().one()
    )
    assert row["status"] == "completed" and row["embedding_model_id"] is None
    assert conn.execute(text("SELECT count(*) FROM knowledge_chunk")).scalar_one() > 1


def test_empty_parsing_result_cannot_be_a_completed_index(environment):
    request, conn, pid = environment
    add_source(conn, pid, "")
    collection = knowledge.project_knowledge(pid, request)["collection_id"]
    knowledge.reindex_collection(collection, request)
    index_id = conn.execute(text("SELECT id FROM knowledge_index")).scalar_one()
    asyncio.run(worker._build_index(index_id))
    source = knowledge.get_collection(collection, request)["sources"][0]
    assert source["index_status"] == "failed"
    assert "没有可索引的文字" in source["index_error"]


def test_failed_preprocessing_is_visible_without_parse_run(environment):
    request, conn, pid = environment
    version, _ = add_source(conn, pid, "暂存原文")
    file_id = conn.execute(
        text("SELECT id FROM project_file WHERE version_id=:v"), {"v": version}
    ).scalar_one()
    conn.execute(text("DELETE FROM element"))
    conn.execute(text("DELETE FROM parse_run"))
    conn.execute(
        text("""INSERT INTO job (id,company_id,project_id,project_file_id,status,stage,
        error_message,finished_at) VALUES ('failed-convert',1,:p,:f,'failed','converting',
        '转换服务拒绝此文件',now())"""),
        {"p": pid, "f": file_id},
    )
    source = knowledge.project_knowledge(pid, request)["sources"][0]
    assert source["state"] == "failed"
    assert source["parse_run_id"] is None
    assert source["error_message"] == "转换服务拒绝此文件"


def test_vectors_only_reused_in_same_embedding_space(environment, monkeypatch):
    request, conn, pid = environment
    add_source(conn, pid, "资质等级要求。")
    own = knowledge.project_knowledge(pid, request)["collection_id"]
    db = KnowledgeStore(request.app.state.components.engine, 1)
    # 使用临时模型行满足索引外键含义，模型调用仍由可控适配器完成。
    config = {"id": None, "model_id": "test-embedding", "signature": "space-one"}
    monkeypatch.setattr(KnowledgeStore, "embedding_config", lambda _: config)

    class Embedding:
        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

        async def aclose(self):
            pass

    monkeypatch.setattr(di, "create_embedding_gateway", lambda _: Embedding())
    knowledge.reindex_collection(own, request)
    index_id = conn.execute(text("SELECT id FROM knowledge_index")).scalar_one()
    asyncio.run(worker._build_index(index_id))
    sources = db.sources([own])
    hits, info = asyncio.run(retrieve_chunks(db, sources, "注册证书", lambda: None,
                                           di.create_embedding_gateway, di.create_rerank_gateway))
    assert hits and info["mode"] == "hybrid"
    current = knowledge.get_collection(own, request)["sources"][0]
    assert current["semantic_ready"] and not current["needs_reindex"]
    config["signature"] = "space-two"
    hits, info = asyncio.run(retrieve_chunks(db, sources, "注册证书", lambda: None,
                                           di.create_embedding_gateway, di.create_rerank_gateway))
    assert not hits and info["mode"] == "keyword"
    changed = knowledge.get_collection(own, request)["sources"][0]
    assert not changed["semantic_ready"] and changed["needs_reindex"]
