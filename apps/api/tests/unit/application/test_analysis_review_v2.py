"""配置修复次数、输入依赖与实际失败轨迹使用真实审查状态机验证。"""

import asyncio
import copy
import json
from dataclasses import replace

import pytest
from synthesis_fixtures import summary_record
from test_analysis_combined_review import approve, execute
from test_analysis_research import block, session

from tender.application.analysis.data import SynthesisRecord, prepare_records
from tender.application.analysis.output import output_schema
from tender.application.analysis.review import _tokens, audit_combined, batches, prompt
from tender.application.analysis.skills import skill_snapshot
from tender.application.analysis.state import published_items
from tender.application.analysis.topic_flow import TopicFlow, TopicIncomplete, identity


async def flow_fixture(repairs=1):
    state, _, _, _ = await execute([summary_record()])
    research = session([block()])
    research.seen = state["research"]["seen"]
    research.limits = replace(research.limits, max_review_repairs=repairs)
    state["topic_flow"]["audit"] = {"round": 0, "results": {}}
    return TopicFlow(state, research)


def issue(payload):
    return {"topic": "a", "detail": "质保范围需补充条件", "kind": "unsupported",
            "record_ids": [payload["record_index"][0]["record_id"]],
            "evidence_ids": ["s1r1c0"], "target": "质保条款"}


@pytest.mark.parametrize("repairs", [0, 1, 2])
def test_configured_repairs_are_bounded_and_never_restart_full_review(repairs):
    async def run():
        flow, packets = await flow_fixture(repairs), []

        async def review(payload):
            packets.append(copy.deepcopy(payload))
            return approve(payload) | {"issues": [issue(payload)]}

        async def save(_):
            pass

        for turn in range(repairs + 1):
            if turn:
                item = flow.state["staged_items"][0]
                item["business"]["conditions"]["expression"] = f"修复条件{turn}"
            done = await audit_combined(flow, review, save)
            assert done == (turn == repairs)
        assert len(packets) == repairs + 1
        assert not packets[0]["repair_issues"]
        assert all(packet["repair_issues"] for packet in packets[1:])
        assert flow.data["audit"]["round"] == repairs
        assert flow.data["audit"]["remaining"]

    asyncio.run(run())


def test_unchanged_repair_ends_without_another_request():
    async def run():
        flow, calls = await flow_fixture(2), []

        async def review(payload):
            calls.append(payload)
            return approve(payload) | {"issues": [issue(payload)]}

        async def save(_):
            pass

        assert not await audit_combined(flow, review, save)
        assert await audit_combined(flow, review, save)
        assert len(calls) == 1 and flow.data["audit"]["remaining"]

    asyncio.run(run())


def test_packets_contain_full_semantic_index_and_direct_source_within_input_limit():
    async def run():
        flow = await flow_fixture()
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=6000)
        packets, _ = batches(flow, "a", [])
        for packet in packets:
            assert packet["protocol"] == "combined-v3"
            assert _tokens(prompt(packet)) + 2048 <= 6000
            assert packet["record_index"][0]["business"]["title"]
            assert any(row["business"]["content"] for row in
                       packet["records"] + packet["context_records"])
            if packet["records"]:
                spans = packet["context_evidence"] + packet["evidence"]
                assert spans[0]["text"] == block()["content"]

    asyncio.run(run())


def test_atomic_clause_is_not_truncated_to_fit_a_small_packet():
    async def run():
        flow = await flow_fixture()
        flow.research.seen["s1r1c0"]["content"] = "完整条件和例外" * 3000
        with pytest.raises(TopicIncomplete, match="超过审查上下文"):
            batches(flow, "a", [])

    asyncio.run(run())


def test_internal_lot_key_is_rejected_before_independent_review():
    record = summary_record(key="lot_1", kind="lot", title="杭州、嘉兴、湖州",
                            scope={"kind": "lots", "lot_refs": ["lot_1"]},
                            quote="杭州、嘉兴、湖州")
    state = {"output_schema": output_schema(skill_snapshot(), "project_basic_info_parsing")}
    seen = {"s1r1c0": block() | {"content": "一 杭州、嘉兴、湖州 1130万元"}}
    with pytest.raises(ValueError, match=r"scope.lot_refs\[0\].*原文编号或名称"):
        prepare_records([SynthesisRecord.model_validate(record)], state, seen,
                        "project_basic_info_parsing")


def test_program_prepares_complete_long_clause_and_keeps_it_with_its_assertion():
    async def run():
        rows = [block() | {"block_id": f"s1r1c{i}", "offset": i,
                            "content": f"长表条款{i}，含条件与例外"} for i in range(8)]
        research = session(rows)
        research.seen = {rows[3]["block_id"]: rows[3]}
        result = await research.review_context({"s1r1c3"})
        assert {r["block_id"] for r in result["blocks"]} == {r["block_id"] for r in rows}
        assert research.tool_calls == 0
        assert research.events[-1]["prepared_for_review"]

    asyncio.run(run())


def test_plan_progress_includes_all_packets_before_the_first_request_and_survives_resume():
    async def run():
        from tender.application.analysis.research import AgentLimits

        limits = AgentLimits(max_output_tokens=500)
        records = [summary_record(key=f"r{i}", content={"字段": f"事项{i}", "内容": "质保三年"})
                   for i in range(5)]
        state, _, _, _ = await execute(records, limits=limits)
        research = session([block()], limits=limits)
        research.seen = state["research"]["seen"]
        research.events = state["research"]["events"]
        state["topic_flow"]["audit"] = {"version": "combined-v3", "round": 0, "results": {}}
        flow, requests, totals = TopicFlow(state, research), [], []

        async def review(payload):
            requests.append(payload)
            totals.append(flow.data["audit"]["progress"]["total_packets"])
            if len(requests) == 2:
                raise RuntimeError("模拟Worker中断")
            return approve(payload)

        async def save(_):
            pass

        with pytest.raises(RuntimeError):
            await audit_combined(flow, review, save)
        first_key = requests[0]
        assert totals[0] > 1 and len(set(totals)) == 1
        requests.clear()

        async def resume(payload):
            requests.append(payload)
            return approve(payload)

        assert await audit_combined(flow, resume, save)
        assert first_key not in requests
        progress = flow.data["audit"]["progress"]
        assert progress["completed_packets"] == progress["total_packets"] == totals[0]

    asyncio.run(run())


@pytest.mark.parametrize("dependency", ["parent", "endpoint", "lot", "requirement"])
def test_dependency_changes_review_only_affected_assertions(dependency):
    async def run():
        flow = await flow_fixture()
        template = flow.state["staged_items"][0]
        items = {}
        for key in ("dependency", "dependent", "independent"):
            item = copy.deepcopy(template)
            item["id"] = key
            item["business"].update(key=key, title=key)
            items[key] = item
        source, dependent = items["dependency"]["business"], items["dependent"]["business"]
        if dependency == "parent":
            source.update(kind="format_node", node_type="group")
            dependent.update(kind="format_node", node_type="section", parent_key="dependency")
        elif dependency == "endpoint":
            dependent.update(kind="relation", predicate="requires", subject_key="dependency",
                             object_key="dependency")
        elif dependency == "requirement":
            source.update(kind="requirement")
            dependent.update(requirement_keys=["dependency"])
        else:
            source.update(kind="lot", title="杭州标段", code="一")
            dependent.update(scope={"kind": "lots", "lot_refs": ["杭州标段"]})
            for item in items.values():
                for ref in item["business"]["citations"]:
                    ref["quote"] = "杭州标段质保三年"
            flow.research.seen["s1r1c0"]["content"] = "杭州标段质保三年"
        flow.state["staged_items"] = list(items.values())
        flow.entries[0]["record_keys"] = list(items)

        async def save(_):
            pass

        async def review(payload):
            return approve(payload)

        assert await audit_combined(flow, review, save)
        packets, _ = batches(flow, "a", [])
        assert not any(packet["records"] for packet in packets)
        source["conditions"]["expression"] = "仅在约定条件下适用"
        packets, _ = batches(flow, "a", [])
        assert {row["record_id"] for packet in packets for row in packet["records"]} == {
            "dependency", "dependent",
        }

    asyncio.run(run())


def test_unchanged_rejected_assertion_is_reused_while_another_assertion_changes():
    async def run():
        flow = await flow_fixture(2)
        first = flow.state["staged_items"][0]
        other = copy.deepcopy(first)
        other["id"] = "other-id"
        other["business"].update(key="other", title="独立事项")
        flow.state["staged_items"].append(other)
        flow.entries[0]["record_keys"].append("other")
        requests = []

        async def review(payload):
            requests.append(payload)
            result = approve(payload)
            if first["id"] in result["reviews"]:
                result["reviews"][first["id"]].update(
                    supported=False, issues=["质保期限缺少明确原文依据"],
                )
            return result

        async def save(_):
            pass

        assert not await audit_combined(flow, review, save)
        other["business"]["conditions"]["expression"] = "独立事项的新条件"
        # 仍存在的唯一问题未发生有效修复，不能再开启下一轮修复碰运气。
        assert await audit_combined(flow, review, save)
        assert len(requests) == 2
        assert {row["record_id"] for row in requests[1]["records"]} == {other["id"]}
        assert first["verification"] == "unsupported"
        assert flow.data["audit"]["round"] == 1
        assert len(flow.data["audit"]["remaining"]) == 1
        assert flow.data["audit"]["issues"][0]["record_keys"] == [first["business"]["key"]]

    asyncio.run(run())


@pytest.mark.parametrize("same_topic", [False, True])
@pytest.mark.parametrize("legacy_cache", [False, True])
def test_unmodified_global_issue_survives_another_record_repair_and_resume(
    same_topic, legacy_cache,
):
    async def run():
        flow = await flow_fixture(2)
        first = flow.state["staged_items"][0]
        second = copy.deepcopy(first)
        second["id"] = "second-id"
        second["business"].update(key="second", title="另一事项")
        flow.state["staged_items"].append(second)
        other_topic = "a" if same_topic else "b"
        if same_topic:
            flow.entries[0]["record_keys"].append("second")
        else:
            entry = copy.deepcopy(flow.entries[0])
            entry.update(topic="b", title="另一主题", record_keys=["second"])
            flow.data["entries"][identity("b", entry["scope"])] = entry
        requests = []

        async def review(payload):
            requests.append(copy.deepcopy(payload))
            result = approve(payload)
            if len(requests) == 1:
                result["issues"] = [
                    {"topic": topic, "kind": "scope", "detail": key + "缺少适用条件",
                     "target": "对应条款", "record_ids": [rid], "evidence_ids": []}
                    for topic, key, rid in (
                        ("a", first["business"]["key"], first["id"]),
                        (other_topic, "second", second["id"]),
                    )
                ]
            return result

        async def save(_):
            pass

        assert not await audit_combined(flow, review, save)
        # 研究状态声明不能代替有效修改；重启后仍须保留未修复问题和否决资格。
        for entry in flow.entries:
            for task in entry["tasks"].values():
                task["status"] = "resolved"
        if legacy_cache:
            flow.data["audit"].pop("issue_inputs", None)
        state = json.loads(json.dumps(flow.state))
        flow = TopicFlow(state, flow.research)
        first, second = flow.state["staged_items"]
        first["business"]["conditions"]["expression"] = "已补充第一项的适用条件"
        assert await audit_combined(flow, review, save)
        assert len(requests) == 2
        assert [row["key"] for row in requests[1]["records"]] == [first["business"]["key"]]
        assert flow.data["audit"]["round"] == 1
        remaining = flow.data["audit"]["remaining"]
        assert len(remaining) == 1 and remaining[0]["record_keys"] == ["second"]
        assert second["review_status"] == "needs_review"
        assert [item["business"]["key"] for item in published_items(flow.state, final=True)] == [
            first["business"]["key"],
        ]

    asyncio.run(run())


def test_global_conflict_is_cleared_when_one_of_its_related_records_changes():
    async def run():
        flow = await flow_fixture()
        first = flow.state["staged_items"][0]
        second = copy.deepcopy(first)
        second["id"] = "second-id"
        second["business"].update(key="second", title="另一事项")
        flow.state["staged_items"].append(second)
        flow.entries[0]["record_keys"].append("second")
        requests = []

        async def review(payload):
            requests.append(copy.deepcopy(payload))
            result = approve(payload)
            if len(requests) == 1:
                result["issues"] = [{"topic": "a", "kind": "conflict",
                    "detail": "两项适用条件冲突", "target": "对应条款",
                    "record_ids": [first["id"], second["id"]], "evidence_ids": []}]
            return result

        async def save(_):
            pass

        assert not await audit_combined(flow, review, save)
        first["business"]["conditions"]["expression"] = "已消除与另一事项的范围冲突"
        assert await audit_combined(flow, review, save)
        assert not flow.data["audit"]["remaining"]
        assert len(requests) == 2 and len(requests[1]["records"]) == 1
        assert len(published_items(flow.state, final=True)) == 2

    asyncio.run(run())


def test_shared_record_keeps_global_issue_identity_for_each_topic_after_unrelated_repair():
    async def run():
        flow = await flow_fixture(2)
        shared = flow.state["staged_items"][0]
        independent = copy.deepcopy(shared)
        independent["id"] = "independent-id"
        independent["business"].update(key="independent", title="独立事项")
        flow.state["staged_items"].append(independent)
        entry = copy.deepcopy(flow.entries[0])
        entry.update(topic="b", title="另一主题")
        flow.data["entries"][identity("b", entry["scope"])] = entry
        flow.entries[0]["record_keys"].append("independent")
        requests = []

        async def review(payload):
            requests.append(copy.deepcopy(payload))
            result = approve(payload)
            if len(requests) == 1:
                result["issues"] = [{"topic": "a", "kind": "scope", "detail": "共享事项缺少条件",
                    "target": "对应条款", "record_ids": [shared["id"]], "evidence_ids": []}]
            return result

        async def save(_):
            pass

        assert not await audit_combined(flow, review, save)
        original_ids = {topic: issue["issue_id"] for issue in flow.data["audit"]["issues"]
                        for topic in issue["topics"]}
        assert set(original_ids) == {"a", "b"}
        independent["business"]["conditions"]["expression"] = "独立事项的新条件"
        assert await audit_combined(flow, review, save)
        remaining = flow.data["audit"]["remaining"]
        assert len(remaining) == 1
        assert {topic: issue["issue_id"] for issue in remaining
                for topic in issue["topics"]} == original_ids
        assert [item["business"]["key"] for item in published_items(flow.state, final=True)] == [
            "independent",
        ]

    asyncio.run(run())


@pytest.mark.parametrize("has_results", [False, True])
def test_stop_reason_reports_concrete_gap_and_actual_publishable_results(has_results):
    async def run():
        from tender.application.analysis.research import AgentLimits

        state = {}
        records = [summary_record(key="unsupported")]
        if has_results:
            records.append(summary_record(key="supported", title="另一个有依据的事项"))

        async def review(payload):
            result = approve(payload)
            for row in payload["records"]:
                if row["key"] == "unsupported":
                    result["reviews"][row["record_id"]].update(
                        supported=False, issues=["质保期限缺少明确原文依据"],
                    )
            return result

        await execute(records, state=state, review=review,
                      limits=AgentLimits(max_review_repairs=0))
        assert state["quality_status"] == "needs_review"
        assert state["topic_flow"]["phase"] == "completed"
        reason = state["stop_reason"]["message"]
        assert "质保期限缺少明确原文依据" in reason
        assert ("已保留1项核实成果" if has_results else "当前没有可发布成果") in reason

    asyncio.run(run())
