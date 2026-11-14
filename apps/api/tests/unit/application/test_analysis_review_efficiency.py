"""分组优化以真实审查计划验证调用数、归属隔离和中断恢复。"""

import asyncio
import copy
import json
from dataclasses import replace

import pytest
from test_analysis_combined_review import approve
from test_analysis_evidence_efficiency import rows
from test_analysis_review_v2 import flow_fixture

from tender.application.analysis.review import (
    _merge_packets,
    audit_combined,
    batches,
    plan_batches,
    review_call_count,
    review_scope,
)
from tender.application.analysis.topic_flow import TopicFlow, identity


async def shared_flow():
    flow = await flow_fixture()
    first = flow.state["staged_items"][0]
    second = copy.deepcopy(first)
    second["id"] = "second"
    second["business"].update(key="second", title="另一事项")
    flow.state["staged_items"].append(second)
    other = copy.deepcopy(flow.entries[0])
    other.update(topic="b", record_keys=["second"], evidence_ids=["s1r1c0", "s1r1c1"])
    flow.data["entries"][identity("b", other["scope"])] = other
    flow.research.seen["s1r1c1"] = rows(2)[1]
    return flow


def test_packet_checks_distinguish_local_records_from_other_packet_navigation():
    async def run():
        flow = await shared_flow()
        first, second = flow.state["staged_items"]
        first["business"]["content"] = {"内容": "甲" * 4000}
        second["business"]["content"] = {"内容": "乙" * 4000}
        second["business"]["scope"] = {"kind": "lots", "lot_refs": ["标段三", "标段四"]}
        other = next(e for e in flow.entries if e["topic"] == "b")
        flow.data["entries"].pop(identity("b", other["scope"]))
        other.update(topic="a", scope=second["business"]["scope"])
        flow.data["entries"][identity("a", other["scope"])] = other
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=10500)
        packets, _ = batches(flow, "a", [])
        assert len(packets) == 2
        for packet in packets:
            local = {row["record_id"] for row in packet["records"]}
            assert len(packet["checks"]) == 2
            assigned = {rid for check in packet["checks"] for rid in check["record_ids"]}
            navigation = {rid for check in packet["checks"]
                          for rid in check["navigation_record_ids"]}
            assert assigned == local
            assert navigation == {first["id"], second["id"]} - local
            assert "导航" in packet["packet_policy"]
        merged = _merge_packets(packets)
        assert not any(check["navigation_record_ids"] for check in merged["checks"])
        assert {rid for check in merged["checks"] for rid in check["record_ids"]} == {
            first["id"], second["id"],
        }

    asyncio.run(run())


def test_partial_shared_evidence_merges_and_budget_matches_actual_requests():
    async def run():
        flow = await shared_flow()
        count = review_call_count(flow, *review_scope(flow))
        assert count == 1
        requests = []

        async def review(payload):
            requests.append(copy.deepcopy(payload))
            assert payload["topics"] == ["a", "b"]
            delivered = payload["evidence"] + payload["context_evidence"]
            assert len(delivered) == len({span["id"] for span in delivered})
            assert not ({r["record_id"] for r in payload["records"]}
                        & {r["record_id"] for r in payload["context_records"]})
            return approve(payload)

        async def save(_):
            pass

        assert await audit_combined(flow, review, save)
        assert len(requests) == count
        assert flow.data["audit"]["progress"]["total_calls"] == count

    asyncio.run(run())


def test_prefetched_shared_call_updates_progress_before_next_group_is_sent():
    from tender.application.analysis.review import _prefetch_small_topics

    async def run():
        flow = await shared_flow()
        first, second = flow.state["staged_items"]
        first["business"]["content"] = {"内容": "甲" * 4000}
        second["business"]["content"] = {"内容": "乙" * 4000}
        second["business"]["scope"] = {"kind": "lots", "lot_refs": ["标段三"]}
        common = copy.deepcopy(flow.entries[0])
        lot = copy.deepcopy(common)
        lot.update(scope=second["business"]["scope"], record_keys=["second"])
        flow.data["entries"] = {identity(topic, entry["scope"]): entry | {"topic": topic}
                                for topic in ("a", "b") for entry in (common, lot)}
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=10500)
        topics, signatures, repair = review_scope(flow)
        assert review_call_count(flow, topics, signatures, repair) == 2
        plans, _ = plan_batches(flow, topics, signatures, repair)
        flow.data["audit"]["progress"] = {"total_calls": 2, "completed_calls": 0}
        calls = []

        async def review(payload):
            if calls:
                # 已成功的合包尚未完成整个主题，界面也必须反映真实调用进度。
                assert flow.data["audit"]["progress"]["completed_calls"] == 1
                raise RuntimeError("第二组合包仍在执行")
            calls.append(payload)
            return approve(payload)

        async def save(_):
            pass

        with pytest.raises(RuntimeError, match="第二组合包仍在执行"):
            await _prefetch_small_topics(flow, topics, signatures, plans, review, save)

    asyncio.run(run())


def test_same_source_dependency_is_only_assigned_to_actual_anchor_owner():
    async def run():
        flow = await shared_flow()
        source_rows = rows(7)
        flow.research.seen.update({r["block_id"]: r for r in source_rows})
        first, second = flow.state["staged_items"]
        second["business"]["citations"][0]["block_id"] = "s1r1c5"
        for entry in flow.entries:
            entry["evidence_ids"] = ["s1r1c0"] if entry["topic"] == "a" else ["s1r1c5"]
        flow.bind_dependencies({"dependencies": {"s1r1c0": ["s1r1c0", "s1r1c1"],
                                                 "s1r1c5": ["s1r1c4", "s1r1c5", "s1r1c6"]}})
        owners = {entry["topic"]: set(entry["evidence_ids"]) for entry in flow.entries}
        assert owners["a"] == {"s1r1c0", "s1r1c1"}
        assert owners["b"] == {"s1r1c4", "s1r1c5", "s1r1c6"}
        assert first["business"]["citations"][0]["block_id"] == "s1r1c0"

    asyncio.run(run())


def test_merge_keeps_full_navigation_and_deduplicates_shared_body():
    async def run():
        flow = await shared_flow()
        packets = [batches(flow, topic, [])[0][0] for topic in ("a", "b")]
        packet = _merge_packets(packets)
        ids = {r["record_id"] for r in packet["records"]}
        assert len(ids) == 2
        assert not ({r["record_id"] for r in packet["context_records"]} & ids)
        assert len(packet["checks"]) == 2
        assert packet["issue_record_ids"] == {"a": [flow.state["staged_items"][0]["id"]],
                                               "b": ["second"]}

    asyncio.run(run())


def test_dependency_ownership_does_not_expand_to_unrelated_scope_of_same_topic():
    async def run():
        flow = await shared_flow()
        owned = next(e for e in flow.entries if e["topic"] == "a")
        unrelated = copy.deepcopy(owned)
        unrelated.update(scope={"kind": "lots", "lot_refs": ["标段二"]},
                         record_keys=[], evidence_ids=["s1r1c5"])
        flow.data["entries"][identity("a", unrelated["scope"])] = unrelated
        flow.bind_dependencies({"dependencies": {"s1r1c0": ["s1r1c0", "s1r1c1"]}})
        assert set(owned["evidence_ids"]) == {"s1r1c0", "s1r1c1"}
        assert unrelated["evidence_ids"] == ["s1r1c5"]
        assert flow.data["evidence_topics"]["s1r1c1"] == ["a", "b"]

    asyncio.run(run())


def test_saved_legacy_packets_do_not_get_regrouped_on_resume():
    async def run():
        flow = await shared_flow()
        topics, signatures, repair = review_scope(flow)
        plans, _ = plan_batches(flow, topics, signatures, repair)
        flow.data["audit"]["packet_plan"] = {"signatures": signatures,
            "topics": {t: copy.deepcopy(packets) for t, (packets, _) in plans.items()}}
        assert review_call_count(flow, topics, signatures, repair) == 2

    asyncio.run(run())


def test_frozen_packets_resume_without_running_new_capacity_planning(monkeypatch):
    async def run():
        flow = await shared_flow()
        topics, signatures, repair = review_scope(flow)
        original, _ = plan_batches(flow, topics, signatures, repair)
        frozen = {t: copy.deepcopy(packets) for t, (packets, _) in original.items()}
        flow.data["audit"]["packet_plan"] = {"signatures": signatures, "topics": frozen}

        def new_capacity_policy(*_args, **_kwargs):
            raise AssertionError("恢复旧冻结请求不能重新应用新分包规则")

        monkeypatch.setattr("tender.application.analysis.review.fits", new_capacity_policy)
        restored, errors = plan_batches(flow, topics, signatures, repair)
        assert not errors
        assert {t: packets for t, (packets, _) in restored.items()} == frozen

    asyncio.run(run())


def test_saved_merged_result_is_projected_without_resending_after_interruption():
    async def run():
        flow = await shared_flow()
        calls = []

        async def review(payload):
            calls.append(payload)
            return approve(payload)

        async def interrupt(_):
            if flow.data["audit"]["results"]:
                raise RuntimeError("回执保存后Worker退出")

        with pytest.raises(RuntimeError):
            await audit_combined(flow, review, interrupt)
        flow = TopicFlow(json.loads(json.dumps(flow.state)), flow.research)
        assert review_call_count(flow, *review_scope(flow)) == 0

        async def save(_):
            pass

        assert await audit_combined(flow, review, save)
        assert len(calls) == 1

    asyncio.run(run())


def test_repair_work_choices_exclude_unrelated_pending_work():
    from tender.application.analysis.search_control import TopicSearch

    async def run():
        flow = await shared_flow()
        flow.data["protocol"] = "research-v3"
        entry = next(e for e in flow.entries if e["topic"] == "a")
        entry["status"] = "researching"
        entry["tasks"] = {key: {"detail": detail, "status": "pending", "record_keys": [],
                                "target": detail, "evidence_ids": []}
                          for key, detail in (("repair", "补齐附件"), ("unrelated", "常规补查"))}
        flow.data["audit"].update(round=1, issues=[{"topic": "a", "record_keys": [],
                                "evidence_ids": [], "target": "补齐附件"}],
                                 issue_task_ids=["repair"])
        choices = TopicSearch(flow).choices(["a", "b"])
        assert [choice["work"] for choice in choices] == ["补齐附件"]

    asyncio.run(run())


def test_unknown_draft_is_retained_but_scope_is_corrected_before_paid_review():
    from synthesis_fixtures import noop

    from tender.application.analysis.agent import ResearchMiddleware

    async def run():
        flow = await flow_fixture()
        flow.state["staged_items"][0]["business"]["scope"] = {"kind": "unknown", "lot_refs": []}
        flow.data.update(phase="synthesis", synthesis_finished=True)
        called = []

        async def review(payload):
            called.append(payload)
            return approve(payload)

        middleware = ResearchMiddleware(flow.research, flow.state, noop, noop,
                                         topic_flow=flow, review_combined=review)
        result = await middleware.advance_research()
        assert result is not None and not called
        assert flow.state["staged_items"][0]["business"]["scope"]["kind"] == "unknown"
        assert flow.data["phase"] == "synthesis"

    asyncio.run(run())


def test_legacy_implicit_merge_keeps_saved_request_identity_before_projection():
    from tender.application.analysis.review import _call_payload
    from tender.application.knowledge.content import fingerprint

    async def run():
        flow = await shared_flow()
        flow.data["audit"]["version"] = "combined-v3"
        next(e for e in flow.entries if e["topic"] == "b")["evidence_ids"] = ["s1r1c0"]
        topics, signatures, repair = review_scope(flow)
        plans, _ = plan_batches(flow, topics, signatures, repair)
        # 真实旧检查点未包含逐事项候选表；冻结旧形状后验证不会改写请求身份。
        for packets, _ in plans.values():
            for packet in packets:
                packet.pop("record_evidence_ids", None)
                packet.pop("check_items", None)
        flow.data["audit"]["packet_plan"] = {"signatures": signatures,
            "topics": {topic: packets for topic, (packets, _) in plans.items()}}
        assert review_call_count(flow, topics, signatures, repair) == 1
        payload = _call_payload(flow, [plans[t][0][0] for t in topics])
        assert "record_evidence_ids" not in payload
        flow.data["audit"]["results"][fingerprint(["combined-v3", payload])] = approve(payload)
        assert review_call_count(flow, topics, signatures, repair) == 0

        async def review(_):
            raise AssertionError("已保存旧合包回执不能再次发送")

        async def save(_):
            pass

        assert await audit_combined(flow, review, save)
        assert len(flow.data["audit"]["completed_topics"]) == 2

    asyncio.run(run())
