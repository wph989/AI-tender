"""提交与刷新复用本次计算；下一次操作重新核对原文和权限。"""

import asyncio
import copy
import json
from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agent_fixtures import KEY, ScriptedRouter, noop, raw, schema
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from test_analysis_agent_workspace import approve
from test_analysis_research import block, session

from tender.application.analysis import drafts
from tender.application.analysis.drafts import DraftWorkspace
from tender.application.analysis.service import AnalysisService
from tender.application.analysis.skill_agent import WorkspaceMiddleware, build_skill_agent
from tender.application.analysis.skills import skill_snapshot
from tender.application.shared.agent_model import RoutedAgentModel
from tender.application.shared.errors import Conflict, NotFound
from tender.domain.analysis.contract import FLOW_VERSION, FLOW_VERSION_KEY, RUNTIME_VERSION


def agent_workspace(resolve=None):
    source = block()
    research = session([source])
    research.seen = {source["block_id"]: source}
    state = {}
    snapshot = skill_snapshot() | {
        KEY + "/references/output_schema.json": json.dumps(schema()),
    }
    graph, _ = build_skill_agent(
        key=KEY, model=RoutedAgentModel(router=ScriptedRouter([])), research=research,
        state=state, snapshot=snapshot, checkpointer=InMemorySaver(), reserve_tool=noop,
        save=noop, resolve_citation=resolve,
    )
    book = DraftWorkspace(state, research.seen, KEY)
    accepted = book.save_records([
        raw(content={"字段": f"事项{i}", "内容": "三年"}) for i in range(40)
    ], "drafts")["accepted"]
    for row in accepted:
        approve(book, row)
    return graph, book, research, accepted


@pytest.mark.parametrize("changed", [None, "quote", "version_id", "page_no"])
def test_final_resolves_each_complete_citation_once(changed):
    async def run():
        calls = []

        async def resolve(ref):
            calls.append(copy.deepcopy(ref))

        graph, book, _, accepted = agent_workspace(resolve)
        if changed:
            # 同一块上的不同引文或定位仍须独立核验，不能仅按 block_id 去重。
            ref = book.state["staged_items"][-1]["business"]["citations"][0]
            ref[changed] = "质保" if changed == "quote" else 2
        tool = graph.nodes["tools"].bound.tools_by_name["submit_analysis"]
        result = await tool.ainvoke({
            "final": True, "record_ids": [row["id"] for row in accepted], "summary": "完成",
        })
        assert result["final"]
        assert len(calls) == (2 if changed else 1)

    asyncio.run(run())


def test_tool_completion_calculates_progress_once_and_event_cannot_mutate_saved_state(monkeypatch):
    async def run():
        _, book, research, _ = agent_workspace()
        count = 0
        original = drafts._ReviewEvaluation.review_current

        def counted(self, rid):
            nonlocal count
            count += 1
            return original(self, rid)

        monkeypatch.setattr(drafts._ReviewEvaluation, "review_current", counted)
        saved = []

        async def save(state):
            saved.append(copy.deepcopy(state["agent_progress"]))

        def event(kind, progress):
            assert kind == "agent_activity" and progress == saved[-1]
            progress["draft_count"] = -1

        middleware = WorkspaceMiddleware(book, research, save, None, noop, None, "", event)

        async def handler(request):
            return ToolMessage(content="ok", tool_call_id=request.tool_call["id"])

        await middleware.awrap_tool_call(
            SimpleNamespace(tool_call={"id": "tool", "name": "update_research"}), handler,
        )
        assert count == 40
        assert book.state["agent_progress"]["draft_count"] == 40
        research.seen["s1r1c0"]["content"] = "质保五年"
        assert book.progress()["reviewed_count"] == 0

    asyncio.run(run())


class RecordStore:
    def __init__(self, issues=False):
        _, book, _, accepted = agent_workspace()
        book.finalize([row["id"] for row in accepted], "完成")
        self.calls = Counter()
        self.revoked = False
        self.source = block()
        self.snapshot = {
            FLOW_VERSION_KEY: FLOW_VERSION,
            KEY + "/references/output_schema.json": json.dumps(schema()),
            "tech_requirement_parsing/references/output_schema.json": json.dumps(schema()),
        }
        business = book.state["draft"]["business_data"]
        if issues:
            business["quality_issues"] = [{"detail": "待核对说明"}]
        self.modules = [
            {"module_key": key, "status": "completed", "business_data": copy.deepcopy(business)}
            for key in (KEY, "tech_requirement_parsing")
        ]

    def report_view(self, report_id, module_keys=None):
        self.calls["report_view"] += 1
        return {"project_id": 10, "runtime_version": RUNTIME_VERSION,
                "source_snapshot": [self.source], "reference_snapshot": [],
                "skill_snapshot": self.snapshot}

    def report_module(self, report_id, module_key):
        return next(module for module in self.modules if module["module_key"] == module_key)

    def report_modules(self, report_id, module_keys=None):
        self.calls["report_modules"] += 1
        return [module for module in self.modules
                if module_keys is None or module["module_key"] in module_keys]

    def collections_for_project(self, project_id):
        return [1]

    def sources(self, allowed):
        self.calls["sources"] += 1
        return [] if self.revoked else [self.source]

    def resolve(self, ref, *, with_content=False):
        self.calls["resolve"] += 1
        if self.revoked:
            raise LookupError("原文已撤销")
        return ref


@pytest.mark.parametrize("issues", [False, True])
def test_empty_quality_issues_skip_sources_but_citations_are_always_rechecked(issues):
    store = RecordStore(issues)
    service = AnalysisService(store, 1, Mock(), Mock())
    result = service.get_module_records(1, KEY)
    assert len(result["records"]) == 40
    assert store.calls["sources"] == int(issues)
    assert store.calls["resolve"] == 1
    store.revoked = True
    hidden = service.get_module_records(1, KEY)
    assert hidden["records"] == [] and hidden["evidence"] == {}
    assert hidden["quality_issues"] == []
    assert store.calls["resolve"] == 2


def test_batch_rechecks_unchanged_records_and_clears_revoked_content():
    store = RecordStore(issues=True)
    service = AnalysisService(store, 1, Mock(), Mock())
    keys = [module["module_key"] for module in store.modules]
    initial = service.get_report_records(1, keys, {})["modules"]
    assert all(len(update["data"]["records"]) == 40 for update in initial)
    assert store.calls == {"report_view": 1, "report_modules": 1, "sources": 1, "resolve": 1}
    versions = {update["module_key"]: update["version"] for update in initial}
    unchanged = service.get_report_records(1, keys, versions)["modules"]
    assert all("data" not in update and update["version"] == versions[update["module_key"]]
               for update in unchanged)
    assert store.calls["resolve"] == 2 and store.calls["sources"] == 2
    store.modules[0]["business_data"]["records"][0]["content"]["内容"] = "五年"
    changed = service.get_report_records(1, keys, versions)["modules"]
    assert "data" in changed[0] and "data" not in changed[1]
    store.revoked = True
    hidden = service.get_report_records(1, keys, versions)["modules"]
    assert all(update["data"]["records"] == [] and update["data"]["quality_issues"] == []
               for update in hidden)
    assert store.calls["resolve"] == 4


def test_bad_module_schema_is_isolated_from_other_topics():
    store = RecordStore()
    store.snapshot[KEY + "/references/output_schema.json"] = "invalid"
    service = AnalysisService(store, 1, Mock(), Mock())
    keys = [module["module_key"] for module in store.modules]
    updates = service.get_report_records(1, [*keys, "missing"], {})["modules"]
    assert "error" in updates[0] and "data" not in updates[0]
    assert len(updates[1]["data"]["records"]) == 40
    assert updates[2] == {"module_key": "missing", "error": "分析维度不存在"}


@pytest.mark.parametrize("prefix", ["x" * 64, "甲" * 22])
def test_unknown_keys_never_enter_skill_column_projection(prefix):
    store = RecordStore()
    store.report_view = Mock(wraps=store.report_view)
    unknown = [prefix + "a", prefix + "b"]
    app = AnalysisService(store, 1, Mock(), Mock())
    updates = app.get_report_records(1, [KEY, *unknown], {})["modules"]
    store.report_view.assert_called_once_with(1, [KEY])
    assert len(updates[0]["data"]["records"]) == 40
    assert updates[1:] == [
        {"module_key": key, "error": "分析维度不存在"} for key in unknown
    ]


def test_unknown_single_topic_uses_protocol_projection_and_returns_not_found():
    store = RecordStore()
    store.report_view = Mock(wraps=store.report_view)
    store.report_module = Mock(return_value=None)
    with pytest.raises(NotFound):
        AnalysisService(store, 1, Mock(), Mock()).get_module_records(1, "x" * 80)
    store.report_view.assert_called_once_with(1, [])


@pytest.mark.parametrize("mode,expected", [
    ("missing", 0), ("revoked", 0), ("mixed", 1), ("visible", 40),
])
def test_display_copies_only_visible_records_and_keeps_nested_content_isolated(
    mode, expected, monkeypatch,
):
    store = RecordStore()
    business = store.modules[0]["business_data"]
    if mode == "missing":
        business["evidence"] = {}
    elif mode == "revoked":
        store.revoked = True
    elif mode == "mixed":
        for record in business["records"][1:]:
            record["evidence_ids"] = ["missing"]
    original = copy.deepcopy(business)
    copied = 0
    original_copy = copy._deepcopy_dispatch[dict]

    def counted(value, memo):
        nonlocal copied
        if value.get("id") and value.get("content"):
            copied += 1
        return original_copy(value, memo)

    monkeypatch.setitem(copy._deepcopy_dispatch, dict, counted)
    result = AnalysisService(store, 1, Mock(), Mock()).get_module_records(1, KEY)
    assert len(result["records"]) == copied == expected
    if result["records"]:
        result["records"][0]["content"]["内容"] = "改写返回正文"
        result["records"][0]["evidence_ids"].append("new")
    assert business == original
    assert store.calls["resolve"] == (0 if mode == "missing" else 1)


@pytest.mark.parametrize("latest", [1, 2, None])
def test_latest_snapshot_check_reads_id_without_loading_full_data_twice(latest):
    store = RecordStore()
    snapshot = {
        "report_id": 1, "id": 1, "revision": 1, "schema_version": "1",
        "input_snapshot": {"source_snapshot": [], "reference_snapshot": [],
                           "module_input_signatures": {}},
        "data": {"schema_version": "1", "lots": [], "facts": [], "requirements": [],
                 "format_nodes": [], "relations": [], "gaps": [], "quality_issues": [],
                 "quality_status": "unknown", "readiness": "unavailable"},
    }
    store.data_snapshot = Mock(return_value=snapshot)
    store.latest_snapshot_id = Mock(return_value=latest)
    store.snapshot_state = Mock(return_value=None)
    store.record_reviews = Mock(return_value={})
    app = AnalysisService(store, 1, Mock(), Mock())
    app.get_report = Mock(return_value={
        "id": 1, "project_id": 10, "status": "completed", "stale": False,
    })
    if latest is None:
        with pytest.raises(Conflict) as error:
            app.get_analysis_data(1)
        assert error.value.code == "data_not_ready"
    else:
        assert app.get_analysis_data(1)["stale"]
    store.data_snapshot.assert_called_once_with(1, None)
    store.latest_snapshot_id.assert_called_once_with(1)
    assert store.snapshot_state.call_count == int(latest == 1)
