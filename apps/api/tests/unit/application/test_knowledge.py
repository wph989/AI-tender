"""验证来源、全文覆盖与工具边界；避免只验证实现的字符串写法。"""

import asyncio
import json

import pytest

from tender.application.analysis_skills import (
    DocumentTools,
    json_completion,
    missing_outline_nodes,
    read_reference,
    run_module,
    scan_document,
)
from tender.application.knowledge import cosine, rank_chunks, split_elements, validate_items
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.domain.errors import (
    ExtractionFailed,
    ExtractionUnavailable,
    InvalidModelOutput,
    ModelRefused,
)
from tender.ports.llm import Completion


def block(source=1, text="投标人须具有甲级资质，不接受联合体。"):
    return {
        "block_id": f"s{source}r1c0",
        "source_id": source,
        "collection_id": source,
        "project_id": source,
        "project_file_id": source,
        "version_id": source,
        "parse_run_id": 1,
        "element_id": source,
        "anchor": "p1b1",
        "page_no": 1,
        "bbox": [0.1, 0.1, 0.8, 0.3],
        "file_name": f"文件{source}.pdf",
        "purpose": "tender",
        "content": text,
        "chapter": "资格条件",
        "offset": 0,
    }


def item(row):
    return {
        "kind": "fact",
        "title": "资格要求",
        "text": row["content"],
        "citations": [{"block_id": row["block_id"], "quote": row["content"]}],
    }


def test_long_tables_are_fully_covered():
    content = "".join(f"第{i}项技术条件。" for i in range(2500))
    chunks = split_elements([{"id": 1, "type": "table", "html": "<table>" + content + "</table>"}])
    covered = set()
    for chunk in chunks:
        covered.update(range(chunk["char_start"], chunk["char_end"]))
    assert covered == set(range(len(" " + content + " ")))
    assert any("第2499项" in c["content"] for c in chunks)


def test_same_anchor_in_different_files_keeps_identity():
    a, b = block(1), block(2)
    items = validate_items([item(a), item(b)], {a["block_id"]: a, b["block_id"]: b})
    assert [i["citations"][0]["source_id"] for i in items] == [1, 2]
    assert items[0]["citations"][0]["version_id"] != items[1]["citations"][0]["version_id"]


def test_unread_or_fabricated_quotes_are_rejected():
    row = block()
    with pytest.raises(ValueError, match="未读取"):
        validate_items([item(row)], {})
    bad = item(row)
    bad["citations"][0]["quote"] = "任何企业均可投标"
    with pytest.raises(ValueError, match="逐字"):
        validate_items([bad], {row["block_id"]: row})


def test_tool_search_covers_all_sources_and_scope_cannot_escape():
    tools = DocumentTools([block(1), block(2)])
    result = tools.execute({"action": "search", "terms": ["甲级"]})
    assert {r["source_id"] for r in result["blocks"]} == {1, 2}
    with pytest.raises(ValueError, match="范围"):
        tools.execute({"action": "read", "source_id": 3})
    with pytest.raises(ValueError):
        read_reference("disqualified_items_parsing", "../../../../../core/settings.py")


def test_hybrid_retrieval_adds_semantic_match_without_keyword_match():
    rows = [
        {"content": "投标保证金", "embedding": [1.0, 0.0]},
        {"content": "应提供担保文件", "embedding": [0.9, 0.1]},
    ]
    assert len(rank_chunks(rows, "保证金")) == 1
    assert len(rank_chunks(rows, "保证金", [1.0, 0.0])) == 2
    with pytest.raises(ValueError, match="维度"):
        cosine([1.0], [1.0, 0.0])


def test_slow_search_embedding_falls_back_to_citable_fulltext_and_closes_client():
    row = block(text="历史设备质保期五年。")

    class Store:
        def embedding_config(self):
            return {"signature": "test-space"}

        def readable_chunks(self, source):
            return [row]

    class SlowEmbedding:
        canceled = False
        closed = False

        async def embed(self, texts):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.canceled = True
                raise

        async def aclose(self):
            self.closed = True

    async def run():
        client = SlowEmbedding()
        hits, info = await asyncio.wait_for(retrieve_chunks(
            Store(), [{"is_parseable": True, "parse_status": "completed"}], "质保期",
            lambda: None, lambda _: client, embedding_timeout=0.01,
        ), timeout=1)
        assert hits[0]["content"] == row["content"]
        assert hits[0]["anchor"] == row["anchor"]
        assert info["mode"] == "keyword" and info["semantic_source_ids"] == []
        assert "等待超时" in info["warning"]
        assert client.canceled and client.closed

    asyncio.run(run())


def test_skill_executes_tools_and_independent_support_check():
    row = block()
    responses = [
        {"action": "search", "terms": ["资质"]},
    ] + [
        {"action": "finish", "items": [item(row)], "relations": []},
        {"supported": [False]},
    ] * 3

    class Model:
        async def complete(self, prompt):
            return Completion(json.dumps(responses.pop(0), ensure_ascii=False), "test")

    items, relations, trace = asyncio.run(
        run_module(
            Model(),
            "personnel_requirement_parsing",
            [row],
            "engineering",
            [],
            [],
            [row["block_id"]],
            lambda: None,
        )
    )
    assert items[0]["kind"] == "insufficient"
    assert items[0]["verification"] == "unsupported"
    assert trace[0]["response"]["blocks"][0]["source_id"] == 1
    assert not relations and not responses


def test_agent_repairs_unsupported_parent_claim_with_full_context():
    row = block(text="商务标。一、资格材料：营业执照复印件须盖章。")
    incomplete = item(row)
    incomplete["text"] = "营业执照复印件属于商务标的资格材料。"
    incomplete["citations"][0]["quote"] = "营业执照复印件须盖章。"
    complete = item(row)
    complete["text"] = incomplete["text"]
    responses = [
        {"action": "read", "source_id": 1},
        {"action": "finish", "items": [incomplete]},
        {"supported": [False]},
        {"action": "finish", "items": [complete]},
        {"supported": [True]},
    ]

    class Model:
        async def complete(self, prompt):
            if len(responses) == 2:
                assert "未获引文支持" in prompt
            return Completion(json.dumps(responses.pop(0), ensure_ascii=False), "test")

    # 旧报告固定其历史协议，不因新节点协议加入而破坏原报告补跑。
    snapshot = {
        "bid_format_outline_parsing/SKILL.md": "历史格式模块，输出 items 和 relations。",
        "__contract__": "按历史 items 协议生成报告，每项附引用。",
    }
    items, _, _ = asyncio.run(
        run_module(
            Model(),
            "bid_format_outline_parsing",
            [row],
            "goods",
            [],
            [],
            [row["block_id"]],
            lambda: None,
            snapshot=snapshot,
        )
    )
    assert items[0]["verification"] == "supported"
    assert items[0]["citations"][0]["quote"] == row["content"]


@pytest.mark.parametrize("repair,duplicate_first", [(True, False), (False, False), (True, True)])
def test_outline_missing_children_are_repaired_or_module_fails(repair, duplicate_first):
    row = block(text="商务标。资格材料：（一）营业执照复印件须盖章。")
    ref = {"block_id": row["block_id"], "quote": row["content"]}
    nodes = [
        {
            "id": "b",
            "name": "商务标",
            "node_type": "group",
            "parent_id": None,
            "requirements": [],
            "citations": [ref],
        },
        {
            "id": "q",
            "name": "资格材料",
            "node_type": "section",
            "parent_id": "b",
            "requirements": ["营业执照复印件须盖章"],
            "citations": [ref],
        },
    ]
    child = {
        "id": "l",
        "name": "营业执照复印件",
        "node_type": "section",
        "parent_id": "q",
        "requirements": ["须盖章"],
        "citations": [ref],
    }

    class Model:
        checks = 0
        reads = 0
        patches = 0

        async def complete(self, prompt):
            if "独立列出格式正文中的材料清单" in prompt:
                self.checks += 1
                assert "requirements" not in prompt and "现有节点" not in prompt
                result = {
                    "outline_inventory": [
                        {
                            "name": child["name"],
                            "block_id": row["block_id"],
                            "quote": row["content"],
                        }
                    ]
                }
            elif "校验每项结论" in prompt:
                result = {"supported": [True] * 3}
            elif "补全格式材料阶段" in prompt:
                self.patches += 1
                additions = [child] if repair else []
                if duplicate_first and self.patches == 1:
                    additions = [nodes[0], child]
                result = {"action": "finish", "outline_nodes": additions}
            elif not self.reads:
                self.reads += 1
                result = {"action": "read", "source_id": 1}
            else:
                result = {
                    "action": "finish",
                    "outline_nodes": nodes,
                }
            return Completion(json.dumps(result, ensure_ascii=False), "test")

    model = Model()
    task = run_module(
        model, "bid_format_outline_parsing", [row], "goods", [], [], [row["block_id"]], lambda: None
    )
    if repair:
        items, _, trace = asyncio.run(task)
        assert len(items) == 3 and items[-1]["cells"]["层级"] == "2"
        assert any(step["response"].get("missing_nodes") for step in trace)
        final_inventory = trace[-1]["response"]["outline_inventory"]
        assert final_inventory[row["block_id"]][0]["name"] == child["name"]
        assert items[0]["title"] == nodes[0]["name"]
        if duplicate_first:
            assert any(
                step.get("phase") == "outline_completion" and "error" in step["response"]
                for step in trace
            )
    else:
        with pytest.raises(ValueError, match="仍遗漏"):
            asyncio.run(task)
    assert model.checks == 1  # 修正不能通过让模型忘记上次找到的原文材料蒙混过关。


def test_outline_inventory_rechecks_new_sources_without_accepting_other_source_names():
    first = block(text="格式正文：授权委托书须签字。")
    second = block(source=2, text="新增标段格式：授权委托书须盖章。")
    inventory = {}

    class Model:
        sources = []

        async def complete(self, prompt):
            rows = json.loads(prompt.split("\n原文：")[1])
            self.sources.append([row["block_id"] for row in rows])
            return Completion(json.dumps({"outline_inventory": [
                {"name": "授权委托书", "block_id": row["block_id"], "quote": row["content"]}
                for row in rows
            ]}, ensure_ascii=False), "test")

    model = Model()
    nodes = [{"name": "授权委托书", "citations": [{"block_id": first["block_id"]}]}]
    seen = {first["block_id"]: first}
    assert asyncio.run(missing_outline_nodes(model, nodes, seen, inventory)) == []
    seen[second["block_id"]] = second
    missing = asyncio.run(missing_outline_nodes(model, nodes, seen, inventory))
    assert [entry["block_id"] for entry in missing] == [second["block_id"]]
    assert model.sources == [[first["block_id"]], [second["block_id"]]]


def test_outline_correction_keeps_read_evidence_and_latest_draft_without_erasing_audit():
    row = block(text="培训安排单独提交。")

    class Model:
        drafts = 0

        async def complete(self, prompt):
            if "独立列出格式正文中的材料清单" in prompt:
                result = {"outline_inventory": []}
            elif "校验每项结论" in prompt:
                result = {"supported": [True]}
            else:
                history = json.loads(prompt.split("\n工具记录：")[1])
                if not history:
                    result = {"action": "read", "source_id": 1}
                else:
                    assert history[0]["response"]["blocks"][0]["content"] == row["content"]
                    assert sum(step["command"]["action"] == "finish" for step in history) <= 1
                    self.drafts += 1
                    result = {"action": "finish", "outline_nodes": [{
                        "id": "training", "name": "培训安排", "node_type": "section",
                        "parent_id": None, "requirements": [],
                        "citations": [{"block_id": row["block_id"],
                                       "quote": "错误引文" if self.drafts < 3 else row["content"]}],
                    }]}
            return Completion(json.dumps(result, ensure_ascii=False), "test")

    items, _, trace = asyncio.run(run_module(
        Model(), "bid_format_outline_parsing", [row], "goods", [], [], [row["block_id"]],
        lambda: None,
    ))
    assert len(items) == 1
    assert sum("error" in step["response"] for step in trace) == 2


@pytest.mark.parametrize("entry", [
    {"name": "授权委托书", "block_id": "outside", "quote": "授权委托书"},
    {"name": "凭空材料", "block_id": "s1r1c0", "quote": "授权委托书"},
])
def test_outline_inventory_rejects_unread_or_fabricated_materials(entry):
    row = block(text="格式正文：授权委托书须签字。")

    class Model:
        async def complete(self, prompt):
            return Completion(json.dumps({"outline_inventory": [entry]}), "test")

    inventory = {}
    with pytest.raises(ValueError):
        asyncio.run(missing_outline_nodes(Model(), [], {row["block_id"]: row}, inventory))
    assert inventory == {}  # 校验失败不能留下半份清单供下一轮误用。


def test_scan_reports_total_before_first_model_request():
    checkpoints = []

    class Model:
        async def complete(self, prompt):
            assert checkpoints == [(0, 1)]
            return Completion('{"candidates":{},"items":[]}', "test")

    asyncio.run(scan_document(Model(), DocumentTools([block()]), lambda *v: checkpoints.append(v)))
    assert checkpoints[-1] == (1, 1)


def test_agent_cannot_finish_without_reading_scanned_candidates():
    row = block()
    replies = [
        {"action": "finish", "items": [], "relations": []},
        {"action": "read", "source_id": row["source_id"]},
        {"action": "finish", "items": [item(row)], "relations": []},
        {"supported": [True]},
    ]

    class Model:
        async def complete(self, prompt):
            if len(replies) == 3:
                assert "请先读取全部候选块" in prompt
            return Completion(json.dumps(replies.pop(0), ensure_ascii=False), "test")

    items, _, trace = asyncio.run(
        run_module(
            Model(),
            "project_basic_info_parsing",
            [row],
            "goods",
            [],
            [],
            [row["block_id"]],
            lambda: None,
        )
    )
    assert items[0]["verification"] == "supported"
    assert trace[0]["response"]["unread_candidates"] == [row["block_id"]]


def test_agent_loads_general_and_lot_specific_skill_rules():
    class Model:
        async def complete(self, prompt):
            context = json.loads(prompt.split("\n任务：", 1)[1].split("\n工具记录：", 1)[0])
            loaded = {r["path"] for r in context["required_rules"]}
            assert loaded == {
                "references/extraction_rules.md",
                "references/output_format.md",
                "references/goods/extraction_rules.md",
                "references/service/extraction_rules.md",
            }
            return Completion('{"action":"finish","items":[],"relations":[]}', "test")

    module = "project_basic_info_parsing"
    paths = [
        "SKILL.md",
        "references/output_format.md",
        "references/extraction_rules.md",
        "references/goods/extraction_rules.md",
        "references/service/extraction_rules.md",
    ]
    snapshot = {f"{module}/{p}": p for p in paths} | {"__contract__": "测试协议"}
    asyncio.run(
        run_module(
            Model(),
            module,
            [],
            "goods",
            [],
            [{"category": "service"}],
            [],
            lambda: None,
            snapshot=snapshot,
        )
    )


def test_module_reads_supplement_even_when_scanner_did_not_assign_it():
    main = block(text="交货期为30日。")
    notice = block(source=2, text="交货期由30日改为45日。")
    current = item(notice) | {"title": "现行交货期", "text": "45日",
                              "citations": item(main)["citations"] + item(notice)["citations"]}
    replies = [
        {"action": "read", "source_id": 1},
        {"action": "finish", "items": [item(main)]},
        {"action": "read", "source_id": 2},
        {"action": "finish", "items": [current]},
        {"supported": [True]},
    ]

    class Model:
        async def complete(self, prompt):
            return Completion(json.dumps(replies.pop(0), ensure_ascii=False), "test")

    items, _, trace = asyncio.run(run_module(
        Model(), "project_basic_info_parsing", [main, notice], "goods", [], [],
        [main["block_id"]], lambda: None,
    ))
    assert trace[1]["response"]["unread_candidates"] == [notice["block_id"]]
    assert items[0]["text"] == "45日" and not replies


@pytest.mark.parametrize("complete", [True, False])
def test_read_but_uncited_candidate_is_independently_extracted_or_rejected(complete):
    license = block(text="未提供营业执照的投标无效。")
    price = block(text="超过最高投标限价的投标予以否决。") | {
        "block_id": "s1r1c1", "offset": 1, "element_id": 2,
    }

    class Model:
        reads = 0
        checks = 0

        async def complete(self, prompt):
            if "候选补漏阶段" in prompt:
                self.checks += 1
                packet = json.loads(prompt.split("\n原文：")[1].split("\n上次补漏")[0])
                assert [row["block_id"] for row in packet] == [price["block_id"]]
                result = {"items": [item(price)] if complete else [], "unrelated_block_ids": []}
            elif "校验每项结论" in prompt:
                result = {"supported": [True, True]}
            elif not self.reads:
                self.reads += 1
                result = {"action": "read", "source_id": 1}
            else:
                result = {"action": "finish", "items": [item(license)]}
            return Completion(json.dumps(result, ensure_ascii=False), "test")

    model = Model()
    task = run_module(model, "disqualified_items_parsing", [license, price], "goods", [], [],
                      [license["block_id"], price["block_id"]], lambda: None)
    if complete:
        items, _, trace = asyncio.run(task)
        assert len(items) == 2 and any("限价" in row["text"] for row in items)
        assert any(step.get("phase") == "candidate_completion" for step in trace)
        assert len(trace[-1]["command"]["items"]) == 2
    else:
        with pytest.raises(ValueError, match="每个候选块"):
            asyncio.run(task)
        assert model.checks == 3


def test_scan_repairs_wrong_phase_output_without_skipping_blocks():
    row = block()
    replies = [
        {"action": "finish", "items": []},
        {"candidates": {"project_basic_info_parsing": [row["block_id"]]}},
    ]

    class Model:
        async def complete(self, prompt):
            assert '"action":"search"' not in prompt
            if len(replies) == 1:
                assert "必须返回 candidates" in prompt
            return Completion(json.dumps(replies.pop(0)), "test")

    candidates, discoveries = asyncio.run(
        scan_document(Model(), DocumentTools([row]), lambda *_: None)
    )
    assert candidates["project_basic_info_parsing"] == [row["block_id"]]
    assert not discoveries


def test_agent_repairs_fabricated_quote_before_persisting_result():
    row = block()
    bad = item(row)
    bad["citations"][0]["quote"] = "不存在的条款"
    replies = [
        {"action": "read", "source_id": 1},
        {"action": "finish", "items": [bad]},
        {"action": "finish", "items": [item(row)]},
        {"supported": [True]},
    ]

    class Model:
        async def complete(self, prompt):
            if len(replies) == 2:
                assert "引文必须逐字" in prompt
            return Completion(json.dumps(replies.pop(0), ensure_ascii=False), "test")

    items, _, trace = asyncio.run(
        run_module(Model(), "project_basic_info_parsing", [row], "goods", [], [], [], lambda: None)
    )
    assert items[0]["citations"][0]["quote"] == row["content"]
    assert "error" in trace[1]["response"]


@pytest.mark.parametrize("first", ["需要读取补充通知", InvalidModelOutput("非法 JSON")])
def test_json_correction_requests_an_action_instead_of_inventing_one(first):
    prompts = []

    class Model:
        async def complete(self, prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                if isinstance(first, Exception):
                    raise first
                return Completion(first, "test")
            return Completion('{"action":"read","source_id":2}', "test")

    result = asyncio.run(json_completion(Model(), "执行模块"))
    assert result == {"action": "read", "source_id": 2}
    assert len(prompts) == 2 and "不能只说明计划" in prompts[1]


def test_repeated_invalid_json_stops_after_two_corrections():
    calls = []

    class Model:
        async def complete(self, prompt):
            calls.append(prompt)
            return Completion("说明：{}", "test")

    with pytest.raises(InvalidModelOutput):
        asyncio.run(json_completion(Model(), "执行模块"))
    assert len(calls) == 3


@pytest.mark.parametrize(
    "error", [ExtractionUnavailable("超时"), ExtractionFailed("配置无效"), ModelRefused("拒绝")]
)
def test_json_correction_never_retries_connection_configuration_or_refusal(error):
    calls = []

    class Model:
        async def complete(self, prompt):
            calls.append(prompt)
            raise error

    with pytest.raises(type(error)):
        asyncio.run(json_completion(Model(), "执行模块"))
    assert len(calls) == 1
