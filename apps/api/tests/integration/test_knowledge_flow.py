"""真实 PostgreSQL 临时表验证索引、检索、问答与报告展示；解析链路由 DeepAgents 专项用例覆盖。"""

import asyncio
import json
import os
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from data_schema import install_data_schema
from langchain_core.messages import AIMessage, message_to_dict
from sqlalchemy import create_engine, text

from tender.adapters.pg.repositories.knowledge.store import KnowledgeStore, sync_sources
from tender.api.analysis import routes as analysis_api
from tender.api.knowledge import routes as knowledge
from tender.api.projects import routes as projects
from tender.api.shared.errors import ApiProblem
from tender.application.analysis.execution import prepare_report
from tender.application.knowledge import execution as knowledge_execution
from tender.application.knowledge.content import fingerprint, validate_items
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
            "knowledge_relation",
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


def attach_completed_module(connection, report_id, blocks):
    """手工写入已完成模块：不跑解析，专测报告展示与关系检索如何处理既有证据。"""
    items = validate_items(
        [
            {
                "field": row["chapter"] or "原文要点",
                "group": "",
                "sort_order": index,
                "values": [
                    {
                        "value": row["content"],
                        "citations": [{"block_id": row["block_id"], "quote": row["content"]}],
                    }
                ],
                "note": "",
            }
            for index, row in enumerate(blocks)
        ],
        {row["block_id"]: row for row in blocks},
    )
    module_id = connection.execute(
        text("""INSERT INTO analysis_module (report_id,module_key,title,status,items)
        VALUES (:report,'project_basic_info_parsing','项目概况','completed',CAST(:items AS JSONB))
        RETURNING id"""),
        {"report": report_id, "items": json.dumps(items, ensure_ascii=False)},
    ).scalar_one()
    return module_id, items


def test_report_items_survive_reparse_and_show_unavailable_when_deleted(environment):
    """报告的读取路径统一：重解析后旧引文仍可溯源，资料删除后降级为不可用而不是消失。"""
    request, conn, pid = environment
    version, run = add_source(conn, pid, "要求甲级资质。")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    # 历史报告（runtime_version=legacy）与新报告共用展示路径，但会被标记为不可再执行。
    conn.execute(
        text("UPDATE analysis_report SET runtime_version='legacy' WHERE id=:id"),
        {"id": report["id"]},
    )
    store = KnowledgeStore(request.app.state.components.engine, 1)
    collection = knowledge.project_knowledge(pid, request)["collection_id"]
    block = store.readable_chunks(store.sources([collection])[0])[0]
    attach_completed_module(conn, report["id"], [block])
    loaded = analysis_api.get_report(report["id"], request)
    assert loaded["runtime_retired"] is True
    reference = loaded["modules"][0]["items"][0]["values"][0]["citations"][0]
    assert reference["version_id"] == version
    assert store.resolve(reference)["parse_run_id"] == run
    conn.execute(
        text("""INSERT INTO parse_run(version_id,provider_version,tier,schema_version,status)
        VALUES (:version,'test','standard','1','completed')"""),
        {"version": version},
    )
    assert analysis_api.get_report(report["id"], request)["stale"] is True
    conn.execute(
        text("UPDATE project_file SET deleted_at=now() WHERE id=:id"),
        {"id": reference["project_file_id"]},
    )
    with pytest.raises(LookupError):
        store.resolve(reference)
    assert (
        analysis_api.get_report(report["id"], request)["modules"][0]["items"][0]["verification"]
        == "unavailable"
    )


def test_unfinished_module_shows_verified_items_saved_in_run_state(environment):
    """未完成模块也展示已核实成果：运行状态里暂存的合格字段合并进结果，失败不白跑。"""
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
        text("""INSERT INTO analysis_module (report_id,module_key,title,status,items)
        VALUES (:report,'project_basic_info_parsing','项目概况','running','[]'::jsonb)
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
                {"staged_items": [item], "staged_items_verified": True}, ensure_ascii=False
            ),
        },
    )
    module = next(
        entry
        for entry in analysis_api.get_report(report["id"], request)["modules"]
        if entry["id"] == module_id
    )
    assert module["status"] == "running"
    assert [entry["field"] for entry in module["items"]] == ["资质"]
    assert module["items"][0]["verification"] == "supported"


def test_report_merges_same_field_versions_and_dedupes_locations(environment):
    """同一字段的多版本在展示时合成一行：值取并集去重、定位去重，历史报告也不重复铺行。"""
    request, conn, pid = environment
    add_source(conn, pid, "质保三年。质保五年。")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    store = KnowledgeStore(request.app.state.components.engine, 1)
    collection = knowledge.project_knowledge(pid, request)["collection_id"]
    block = store.readable_chunks(store.sources([collection])[0])[0]
    items = validate_items(
        [
            {
                "field": "质保期",
                "group": "质保",
                "sort_order": 2,
                "values": [
                    {
                        "value": "质保三年",
                        "citations": [{"block_id": block["block_id"], "quote": "质保三年"}],
                    }
                ],
                "note": "",
            },
            {
                "field": "质保期",
                "group": "质保",
                "sort_order": 2,
                "values": [
                    {
                        "value": "质保三年",
                        "citations": [{"block_id": block["block_id"], "quote": "质保三年"}],
                    },
                    {
                        "value": "质保五年",
                        "citations": [{"block_id": block["block_id"], "quote": "质保五年"}],
                    },
                ],
                "note": "",
            },
        ],
        {block["block_id"]: block},
    )
    for entry in items:
        entry["verification"] = "supported"
    # 模拟改造前的历史记录：值“质保五年”借用了同一元素里“质保三年”的摘录。
    items[1]["values"][1]["citations"][0]["quote"] = "质保三年"
    conn.execute(
        text("""INSERT INTO analysis_module (report_id,module_key,title,status,items)
        VALUES (:report,'project_basic_info_parsing','项目概况','completed',
                CAST(:items AS JSONB))"""),
        {"report": report["id"], "items": json.dumps(items, ensure_ascii=False)},
    )
    module = analysis_api.get_report(report["id"], request)["modules"][0]
    assert [entry["field"] for entry in module["items"]] == ["质保期"]
    assert [value["value"] for value in module["items"][0]["values"]] == ["质保三年", "质保五年"]
    assert len(module["items"][0]["values"][0]["citations"]) == 1
    # 展示时按值回查元素原文：错位的历史摘录收敛到值真正出现的位置。
    located = module["items"][0]["values"][1]["citations"][0]["quote"]
    assert "质保五年" in located


@pytest.mark.parametrize("legacy_ids", [False, True])
def test_report_preserves_outline_nodes_with_different_parent_paths(environment, legacy_ids):
    """新报告和旧报告展示都不能把同名材料跨父级合并，避免编制要求失去归属。"""
    request, conn, pid = environment
    content = "商务标。甲标段营业执照须盖章。乙标段营业执照须签字。"
    add_source(conn, pid, content)
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    store = KnowledgeStore(request.app.state.components.engine, 1)
    collection = knowledge.project_knowledge(pid, request)["collection_id"]
    block = store.readable_chunks(store.sources([collection])[0])[0]
    # 只构造旧报告的已存历史形状；兼容读取不应依赖已下线的旧格式生成器。
    history = [
        ("root", "商务标", "商务标", "无"),
        ("lot-a", "甲标段", "甲标段", "商务标"),
        ("license-a", "营业执照", "须盖章", "商务标 / 甲标段"),
        ("lot-b", "乙标段", "乙标段", "商务标"),
        ("license-b", "营业执照", "须签字", "商务标 / 乙标段"),
    ]
    items = validate_items([{
        "field": name, "group": "商务标", "note": "上级路径：" + parent_path,
        "sort_order": order, "values": [{
            "value": value, "citations": [{"block_id": block["block_id"], "quote": content}],
        }],
    } for order, (_, name, value, parent_path) in enumerate(history)], {block["block_id"]: block})
    for item, (node_id, _, _, _) in zip(items, history, strict=True):
        item["verification"] = "supported"
        item["id"] = fingerprint(["outline", node_id])[:20]
        if legacy_ids:
            item["id"] = fingerprint([item["field"], item["values"]])[:20]
    conn.execute(
        text("""INSERT INTO analysis_module (report_id,module_key,title,status,items)
        VALUES (:report,'bid_format_outline_parsing','格式大纲','completed',
                CAST(:items AS JSONB))"""),
        {"report": report["id"], "items": json.dumps(items, ensure_ascii=False)},
    )
    displayed = analysis_api.get_report(report["id"], request)["modules"][0]["items"]
    assert len(displayed) == 5
    licenses = [item for item in displayed if item["field"] == "营业执照"]
    assert [item["note"].split("上级路径：")[1] for item in licenses] == [
        "商务标 / 甲标段", "商务标 / 乙标段"
    ]
    assert [item["values"][0]["value"] for item in licenses] == ["须盖章", "须签字"]


def test_retired_runtime_report_cannot_run_or_retry(environment):
    """旧流程报告只读：worker 拒绝执行，补跑接口报错而不是静默改写历史数据。"""
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    conn.execute(
        text("UPDATE analysis_report SET runtime_version='legacy' WHERE id=:id"),
        {"id": report["id"]},
    )
    asyncio.run(worker._analyze_project(report["id"]))
    retired = analysis_api.get_report(report["id"], request)
    assert retired["status"] == "failed" and "已下线" in retired["error_message"]
    with pytest.raises(ApiProblem) as exc:
        analysis_api.retry_report(report["id"], analysis_api.RetryInput(), request)
    assert exc.value.status_code == 409 and exc.value.code == "runtime_retired"


def test_reference_snapshot_change_marks_only_current_runtime_reports_stale(environment):
    """参考来源快照只有当前运行时会记录：旧报告不能因库里存在参考来源就被误判为已变化。"""
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
    # 同一份报告标记为旧运行时后，同样的参考来源不能触发 stale：旧流程从不记录参考快照。
    conn.execute(
        text("UPDATE analysis_report SET runtime_version='legacy' WHERE id=:id"),
        {"id": report["id"]},
    )
    retired = analysis_api.get_report(report["id"], request)
    assert retired["runtime_retired"] is True and retired["stale"] is False


def test_wait_for_missing_sources_or_explicit_partial_analysis(environment):
    """深运行时的准备阶段：资料不完整且未勾选部分分析时中止，勾选后只固定可用批次。"""
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    add_source(conn, pid, "未完成解析的资质要求。", status="failed")
    configure(request, pid)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    with pytest.raises(ValueError, match="未完整解析"):
        prepare_report(worker._store(), analysis_api.report_row(request, report["id"]))
    analysis_api.cancel_report(report["id"], request)
    partial = analysis_api.start_analysis(
        pid, analysis_api.AnalysisInput(allow_partial=True), request
    )
    fixed, sources = prepare_report(
        worker._store(), analysis_api.report_row(request, partial["id"])
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
    conn.execute(
        text("UPDATE analysis_report SET status='completed' WHERE id=:id"), {"id": report["id"]}
    )
    module_id, items = attach_completed_module(conn, report["id"], [block])
    conn.execute(
        text("""INSERT INTO knowledge_relation
        (report_id,module_id,subject,predicate,object,citations,verified)
        VALUES (:r,:m,'甲级资质','需要','证书',CAST(:refs AS JSONB),true)"""),
        {
            "r": report["id"],
            "m": module_id,
            "refs": json.dumps(items[0]["values"][0]["citations"], ensure_ascii=False),
        },
    )
    _, relations = knowledge_execution.graph_expand(store, pid, [block], sources)
    assert len(relations) == 1
    changed_sources = [sources[0] | {"parse_run_id": sources[0]["parse_run_id"] + 1}]
    _, relations = knowledge_execution.graph_expand(store, pid, [block], changed_sources)
    assert not relations


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
    with pytest.raises(ApiProblem) as exc:
        knowledge.ask_project(
            pid, knowledge.AskInput(question="资质", collection_ids=[library["id"]]), request
        )
    assert exc.value.status_code == 403
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
    conn.execute(
        text("UPDATE analysis_report SET status='completed' WHERE id=:id"), {"id": report["id"]}
    )
    module_id, items = attach_completed_module(conn, report["id"], blocks)
    refs = [ref for item in items for value in item["values"] for ref in value["citations"]]
    conn.execute(
        text("""INSERT INTO knowledge_relation
        (report_id,module_id,subject,predicate,object,citations,verified)
        VALUES (:r,:m,'甲级资质','需要','履约保函',CAST(:refs AS JSONB),true)"""),
        {"r": report["id"], "m": module_id, "refs": json.dumps(refs, ensure_ascii=False)},
    )

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
