"""真实 PostgreSQL 临时表验证完整分析链路；模型用可控适配器，业务数据不写入。"""

import asyncio
import json
import os
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from tender.api import knowledge, projects
from tender.application.knowledge_store import KnowledgeStore, sync_sources
from tender.core import settings
from tender.ports.llm import Completion
from tender.worker import knowledge as worker

pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证"
)


@pytest.fixture
def environment(monkeypatch):
    # 本文件验证已发布的历史快照；DeepAgents 多连接/恢复场景有独立集成用例。
    monkeypatch.setattr(knowledge, "RUNTIME_VERSION", "legacy")
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
        facade = SimpleNamespace(
            connect=lambda: nullcontext(connection), begin=lambda: nullcontext(connection)
        )
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(components=SimpleNamespace(engine=facade))),
            headers={},
        )
        monkeypatch.setattr(settings, "company_id", lambda: 1)
        monkeypatch.setattr(worker, "_engine", facade)
        monkeypatch.setattr(worker, "_model", lambda _: FixtureModel())
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
    async def complete(self, prompt):
        if "独立列出格式正文中的材料清单" in prompt:
            result = {"outline_inventory": []}
        elif "候选补漏阶段" in prompt:
            packet = json.loads(prompt.split("\n原文：")[1])
            result = {"items": [], "unrelated_block_ids": [row["block_id"] for row in packet]}
        elif "校验每项结论" in prompt:
            items = json.loads(prompt.split("\n", 1)[1])
            result = {"supported": [True] * len(items)}
        elif "全文扫描阶段" in prompt:
            packet = json.loads(prompt.split("原文：", 1)[1])
            result = {
                "candidates": {"project_basic_info_parsing": [r["block_id"] for r in packet]},
                "items": [],
            }
        elif "\n任务：" in prompt:
            history = json.loads(prompt.split("\n工具记录：")[1])
            context = json.loads(prompt.split("\n任务：")[1].split("\n工具记录：")[0])
            if context.get("output_schema") == "outline_nodes":
                read_ids = {
                    row["block_id"] for step in history
                    for row in step["response"].get("blocks", [])
                }
                unread = next((loc for loc in context["candidate_locations"]
                               if loc["block_id"] not in read_ids), None)
                result = ({"action": "read", "source_id": unread["source_id"],
                           "offset": unread["offset"]} if unread
                          else {"action": "finish", "outline_nodes": []})
            elif not history:
                result = {"action": "search", "terms": ["资质"]}
            else:
                hits = history[-1]["response"]["blocks"]
                result = {
                    "action": "finish",
                    "relations": [],
                    "items": [
                        {
                            "kind": "fact",
                            "title": h["file_name"],
                            "text": h["content"],
                            "citations": [{"block_id": h["block_id"], "quote": h["content"]}],
                        }
                        for h in hits
                    ],
                }
        else:
            hits = json.loads(prompt.split("\n原文：")[1].split("\n已校验关系：")[0])
            result = {
                "items": [
                    {
                        "kind": "fact",
                        "title": "资质要求",
                        "text": h["content"],
                        "citations": [{"block_id": h["block_id"], "quote": h["content"]}],
                    }
                    for h in hits
                ]
            }
        return Completion(json.dumps(result, ensure_ascii=False), "fixture")

    async def aclose(self):
        pass


def configure(request, pid):
    knowledge.save_settings(pid, knowledge.AnalysisSettings(category="engineering"), request)


def test_all_files_report_and_old_run_citation_survive_reparse(environment):
    request, conn, pid = environment
    first_version, first_run = add_source(conn, pid, "要求甲级资质。")
    add_source(conn, pid, "补遗：要求乙级资质。")
    configure(request, pid)
    result = knowledge.start_analysis(pid, knowledge.AnalysisInput(), request)
    asyncio.run(worker._analyze_project(result["id"]))
    report = knowledge.get_report(result["id"], request)
    assert report["status"] == "completed"
    assert report["coverage"]["scanned_blocks"] == report["coverage"]["total_blocks"] == 2
    refs = [item["citations"][0] for item in report["modules"][0]["items"]]
    assert len({ref["version_id"] for ref in refs}) == 2
    assert {ref["anchor"] for ref in refs} == {"p1b1"}
    ref = next(r for r in refs if r["version_id"] == first_version)
    conn.execute(
        text("""INSERT INTO parse_run(version_id,provider_version,tier,schema_version,status)
        VALUES (:version,'test','standard','1','completed')"""),
        {"version": first_version},
    )
    store = KnowledgeStore(request.app.state.components.engine, 1)
    assert store.resolve(ref)["parse_run_id"] == first_run
    assert knowledge.get_report(result["id"], request)["stale"] is True
    conn.execute(
        text("UPDATE project_file SET deleted_at=now() WHERE id=:id"),
        {"id": ref["project_file_id"]},
    )
    with pytest.raises(LookupError):
        store.resolve(ref)
    assert any(
        item["verification"] == "unavailable"
        for item in knowledge.get_report(result["id"], request)["modules"][0]["items"]
    )


def test_wait_for_all_and_explicit_partial_analysis(environment):
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    add_source(conn, pid, "未完成解析的资质要求。", status="failed")
    configure(request, pid)
    result = knowledge.start_analysis(pid, knowledge.AnalysisInput(), request)
    asyncio.run(worker._analyze_project(result["id"]))
    failed = knowledge.get_report(result["id"], request)
    assert failed["status"] == "failed"
    assert "未完整解析" in failed["error_message"]
    partial = knowledge.start_analysis(pid, knowledge.AnalysisInput(allow_partial=True), request)
    asyncio.run(worker._analyze_project(partial["id"]))
    report = knowledge.get_report(partial["id"], request)
    assert report["status"] == "partial" and report["coverage"]["partial"]
    assert report["coverage"]["scanned_blocks"] == 1


def test_retry_before_scan_waits_for_repaired_sources(environment):
    request, conn, pid = environment
    _, run = add_source(conn, pid, "要求甲级资质。", status="failed")
    configure(request, pid)
    result = knowledge.start_analysis(pid, knowledge.AnalysisInput(), request)
    asyncio.run(worker._analyze_project(result["id"]))
    assert knowledge.get_report(result["id"], request)["status"] == "failed"
    conn.execute(text("UPDATE parse_run SET status='completed' WHERE id=:id"), {"id": run})
    retried = knowledge.retry_report(result["id"], knowledge.RetryInput(), request)
    assert retried["status"] == "waiting"
    asyncio.run(worker._analyze_project(result["id"]))
    assert knowledge.get_report(result["id"], request)["status"] == "completed"


def test_retry_only_executes_selected_failed_modules(environment, monkeypatch):
    request, conn, pid = environment
    add_source(conn, pid, "要求甲级资质。")
    configure(request, pid)
    result = knowledge.start_analysis(pid, knowledge.AnalysisInput(), request)
    original = worker.run_module
    selected = "project_basic_info_parsing"
    untouched = "disqualified_items_parsing"
    calls = []

    async def fail_two(model, key, *args, **kwargs):
        if key in {selected, untouched}:
            raise ValueError("测试供应商故障")
        return await original(model, key, *args, **kwargs)

    monkeypatch.setattr(worker, "run_module", fail_two)
    asyncio.run(worker._analyze_project(result["id"]))
    assert knowledge.get_report(result["id"], request)["status"] == "partial"

    async def record(model, key, *args, **kwargs):
        calls.append(key)
        return await original(model, key, *args, **kwargs)

    monkeypatch.setattr(worker, "run_module", record)
    knowledge.retry_report(result["id"], knowledge.RetryInput(module_keys=[selected]), request)
    asyncio.run(worker._analyze_project(result["id"]))
    report = knowledge.get_report(result["id"], request)
    states = {module["module_key"]: module["status"] for module in report["modules"]}
    assert calls == [selected]
    assert states[selected] == "completed"
    assert states[untouched] == "failed"
    assert report["status"] == "partial"


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
    with pytest.raises(knowledge.ApiProblem) as exc:
        knowledge.ask_project(
            pid, knowledge.AskInput(question="资质", collection_ids=[library["id"]]), request
        )
    assert exc.value.status_code == 403
    question = knowledge.ask_project(pid, knowledge.AskInput(question="资质"), request)
    asyncio.run(worker._answer_question(question["id"]))
    answer = knowledge.get_answer(question["id"], request)
    assert answer["status"] == "completed"
    assert all(ref["collection_id"] == own_id for i in answer["items"] for ref in i["citations"])


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

    monkeypatch.setattr(worker, "create_embedding_gateway", lambda _: Embedding())
    knowledge.reindex_collection(own, request)
    index_id = conn.execute(text("SELECT id FROM knowledge_index")).scalar_one()
    asyncio.run(worker._build_index(index_id))
    sources = db.sources([own])
    hits, info = asyncio.run(worker.retrieve(db, sources, "注册证书", lambda: None))
    assert hits and info["mode"] == "hybrid"
    current = knowledge.get_collection(own, request)["sources"][0]
    assert current["semantic_ready"] and not current["needs_reindex"]
    config["signature"] = "space-two"
    hits, info = asyncio.run(worker.retrieve(db, sources, "注册证书", lambda: None))
    assert not hits and info["mode"] == "keyword"
    changed = knowledge.get_collection(own, request)["sources"][0]
    assert not changed["semantic_ready"] and changed["needs_reindex"]


def test_graph_expansion_rejects_old_parse_evidence(environment):
    request, conn, pid = environment
    add_source(conn, pid, "甲级资质应提供证书。")
    own = knowledge.project_knowledge(pid, request)["collection_id"]
    configure(request, pid)
    report = knowledge.start_analysis(pid, knowledge.AnalysisInput(), request)
    asyncio.run(worker._analyze_project(report["id"]))
    db = KnowledgeStore(request.app.state.components.engine, 1)
    sources = db.sources([own])
    blocks = db.readable_chunks(sources[0])
    module = knowledge.get_report(report["id"], request)["modules"][0]
    reference = module["items"][0]["citations"][0]
    conn.execute(
        text("""INSERT INTO knowledge_relation
        (report_id,module_id,subject,predicate,object,citations,verified)
        VALUES (:r,:m,'甲级资质','需要','证书',CAST(:refs AS JSONB),true)"""),
        {"r": report["id"], "m": module["id"], "refs": json.dumps([reference], ensure_ascii=False)},
    )
    _, relations = worker.graph_expand(db, pid, blocks[:1], sources)
    assert len(relations) == 1
    changed_sources = [sources[0] | {"parse_run_id": sources[0]["parse_run_id"] + 1}]
    _, relations = worker.graph_expand(db, pid, blocks[:1], changed_sources)
    assert not relations
