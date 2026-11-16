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


def test_changed_review_policy_cannot_reuse_saved_approval(monkeypatch):
    from tender.application.analysis import review as module
    from tender.application.analysis.state import published_items

    async def run():
        flow = await flow_fixture(repairs=0)
        calls = []
        interrupted = False

        async def review(payload):
            calls.append(copy.deepcopy(payload))
            result = approve(payload)
            if len(calls) > 1:
                for verdict in result["reviews"].values():
                    verdict.update(supported=False, issues=["旧现场要求与项目电子开标方式冲突"])
            return result

        async def save(_):
            nonlocal interrupted
            # 复现回执已保存、尚未投影时升级审查规则；新规则不能沿用旧请求的通过回执。
            if not interrupted and flow.data["audit"]["results"]:
                interrupted = True
                raise ConnectionError("旧审查回执已保存")

        with pytest.raises(ConnectionError, match="旧审查回执"):
            await audit_combined(flow, review, save)
        monkeypatch.setattr(module, "REVIEW_RULES", module.REVIEW_RULES + "\n新增明确适用性要求")
        assert await audit_combined(flow, review, save)
        assert len(calls) == 2
        assert not published_items(flow.state, final=True)
        assert flow.data["audit"]["remaining"]

    asyncio.run(run())


def test_missing_source_disposition_reaches_review_and_invalidates_old_topic_completion():
    from tender.application.analysis.review import reviewed_topics

    async def run():
        flow = await flow_fixture()

        async def review(payload):
            return approve(payload)

        async def save(_):
            pass

        assert await audit_combined(flow, review, save)
        assert reviewed_topics(flow) == {"a"}
        # 研究已核清缺件而草稿正文未变时，不能静默沿用“已核清完整资料”的旧主题资格。
        note = {"status": "missing_source", "detail": "已核清目录，附件甲未随项目提供",
                "evidence_ids": ["s1r1c0"], "notes": ["重复研究叙述" * 600]}
        flow.entries[0]["dispositions"] = {"w1": note, "w2": copy.deepcopy(note)}
        assert reviewed_topics(flow) == set()
        packets, _ = batches(flow, "a", [])
        findings = [hint for packet in packets for check in packet["checks"]
                    for hint in check.get("input_findings", [])]
        assert findings and findings[0]["detail"] == note["detail"]
        assert all(hint["evidence_ids"] for hint in findings)
        assert "重复研究叙述" not in json.dumps(packets, ensure_ascii=False)
        for packet in packets:
            shown = {e["id"] for e in packet["evidence"] + packet["context_evidence"]}
            assert all(set(hint["evidence_ids"]) <= shown for check in packet["checks"]
                       for hint in check.get("input_findings", []))

    asyncio.run(run())


@pytest.mark.parametrize("explicit_dependency", [False, True])
def test_large_chunks_keep_explicit_dependencies_without_automatic_whole_section_neighbours(
    explicit_dependency,
):
    async def run():
        flow = await flow_fixture()
        original = flow.research.seen["s1r1c0"]
        original["chunk_version"] = "2"
        other = original | {"block_id": "s1r1c1", "element_id": 2, "offset": 1,
                            "content": "另一节的独立事项及条件。"}
        flow.research.seen[other["block_id"]] = other
        flow.entries[0]["evidence_ids"].append(other["block_id"])
        record = flow.state["staged_items"][0]
        if explicit_dependency:
            record["review_evidence_ids"] = [other["block_id"]]
        packets, _ = batches(flow, "a", [])
        primary = next(p for p in packets if p["records"])
        expected = {"s1r1c0", "s1r1c1"} if explicit_dependency else {"s1r1c0"}
        assert set(primary["record_evidence_ids"][record["id"]]) == expected
        # 其它已读正文仍接受查漏；不把相关性优化变成丢弃原文或免审。
        assert {e["id"] for p in packets for e in p["evidence"] + p["context_evidence"]} == {
            "s1r1c0", "s1r1c1",
        }
        assert record["id"] not in {r["record_id"] for r in primary["record_index"]}

    asyncio.run(run())


def test_additional_evidence_packet_does_not_repeat_complete_check_responsibility():
    async def run():
        flow = await flow_fixture()
        flow.research.seen["s1r1c0"]["chunk_version"] = "2"
        flow.state["staged_items"][0]["business"]["content"] = {"内容": "已确认条款" * 400}
        extra = flow.research.seen["s1r1c0"] | {
            "block_id": "s1r1c1", "offset": 1, "element_id": 2,
            "content": "补充条款" * 1100,
        }
        flow.research.seen[extra["block_id"]] = extra
        flow.entries[0]["evidence_ids"].append(extra["block_id"])
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=11000)
        repair = [{"topic": "a", "kind": "unsupported", "action": "repair",
                   "issue_id": "a" * 64, "detail": "原条款条件需要核对", "target": "原条款",
                   "record_keys": [flow.state["staged_items"][0]["business"]["key"]],
                   "evidence_ids": ["s1r1c0"]}]
        packets, _ = batches(flow, "a", repair)
        assert len(packets) == 2
        primary, additional = packets
        assert primary["check_items"]
        assert additional["check_items"] == []
        # 补充包仍逐块查漏，发现真实遗漏时须进入原问题账，不能因此免审或丢掉证据。
        assert additional["checks"] and additional["evidence"][0]["id"] == "s1r1c1"
        assert additional["record_index"]
        assert primary["repair_issues"] == repair
        assert additional["repair_issues"] == []
        frozen, _ = batches(flow, "a", [], frozen_packets=copy.deepcopy(packets))
        assert frozen == packets

        calls = []

        async def review(payload):
            calls.append(payload)
            result = approve(payload)
            if not payload["check_items"]:
                result["issues"] = [{"topic": "a", "kind": "omission", "action": "repair",
                    "detail": "补充条款规定的独立费用未提取", "target": "独立费用",
                    "record_ids": [], "evidence_ids": ["s1r1c1"]}]
            return result

        async def save(_):
            pass

        assert not await audit_combined(flow, review, save)
        assert len(calls) == 2
        assert any(i["target"] == "独立费用" for i in flow.data["audit"]["issues"])

    asyncio.run(run())


def test_research_narrative_does_not_displace_complete_evidence_in_review():
    async def run():
        flow = await flow_fixture()
        flow.state["research_completed"] = {"research_summary": "研究过程的重复说明" * 1200}
        repair = [{"topic": "a", "kind": "reference", "action": "read",
                   "issue_id": "a" * 64, "detail": "核对原文约定的完整条件", "target": "条款",
                   "record_keys": [flow.state["staged_items"][0]["business"]["key"]],
                   "evidence_ids": ["s1r1c0"]}]
        flow.entries[0]["tasks"]["review-question"] = repair[0] | {
            "task_id": "review-question", "review_issue": True, "status": "pending",
        }
        packets, _ = batches(flow, "a", repair)
        primary, = packets
        assert primary["repair_issues"] == repair
        assert primary["records"][0]["business"]["content"]
        assert next(e["text"] for e in primary["evidence"] + primary["context_evidence"]
                    if e["id"] == "s1r1c0") == flow.research.seen["s1r1c0"]["content"]
        # 复核问题只传一次，独立审查始终消费完整事项、真实原文和结构化研究账。
        assert all(not c["tasks"] for c in primary["checks"])

    asyncio.run(run())


def test_shared_source_does_not_pull_another_records_repair_candidates_into_every_packet():
    async def run():
        flow = await flow_fixture()
        first = flow.state["staged_items"][0]
        second = copy.deepcopy(first)
        second["id"] = "second"
        second["business"].update(key="second", title="第二事项")
        first["business"]["content"] = {"内容": "甲" * 2000}
        flow.state["staged_items"].append(second)
        flow.entries[0]["record_keys"].append("second")
        source = flow.research.seen["s1r1c0"]
        source["chunk_version"] = "2"
        flow.research.seen["s1r1c8"] = source | {
            "block_id": "s1r1c8", "offset": 8, "element_id": 9, "content": "乙" * 4000,
        }
        second["review_evidence_ids"] = ["s1r1c8"]
        flow.entries[0]["evidence_ids"].append("s1r1c8")
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=11000)
        repair = [{"topic": "a", "kind": "conflict", "action": "read",
                   "issue_id": "b" * 64, "detail": "核对第二事项的修订", "target": "第二事项",
                   "record_keys": ["second"], "evidence_ids": ["s1r1c0"]}]
        packets, _ = batches(flow, "a", repair)
        primary = next(p for p in packets
                       if any(r["record_id"] == first["id"] for r in p["records"]))
        assert primary["repair_issues"] == []
        assert "s1r1c8" not in {e["id"] for e in primary["evidence"] + primary["context_evidence"]}
        owner = next(p for p in packets if p["repair_issues"])
        assert "second" in {r["key"] for r in owner["records"] + owner["context_records"]}
        assert "s1r1c8" in {e["id"] for e in owner["evidence"] + owner["context_evidence"]}

    asyncio.run(run())


@pytest.mark.parametrize("conflict", [False, True])
def test_candidate_overflow_keeps_complete_record_in_each_part_and_combines_verdicts(conflict):
    from tender.application.analysis.review import fits
    from tender.application.analysis.state import published_items

    async def run():
        flow = await flow_fixture(repairs=0)
        item = flow.state["staged_items"][0]
        anchor = flow.research.seen["s1r1c0"]
        anchor["chunk_version"] = "2"
        extras = [f"s1r1c{i}" for i in range(1, 4)]
        for offset, key in enumerate(extras, 1):
            flow.research.seen[key] = anchor | {
                "block_id": key, "offset": offset, "element_id": offset + 1,
                "content": "需要逐条核对的补充候选原文。" * 180,
            }
        item["review_evidence_ids"] = extras
        flow.entries[0]["evidence_ids"].extend(extras)
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=10500)
        packets, _ = batches(flow, "a", [])
        assert len(packets) > 1
        assert all(fits(p, flow.research.limits) for p in packets)
        full_record = packets[0]["records"][0]
        assert all(p["records"] == [full_record] for p in packets)
        assert all("s1r1c0" in p["record_evidence_ids"][item["id"]] for p in packets)
        assert {key for p in packets for key in p["record_evidence_ids"][item["id"]]} == {
            "s1r1c0", *extras,
        }
        calls = []

        async def review(payload):
            calls.append(payload)
            result = approve(payload)
            if conflict and extras[-1] in payload["record_evidence_ids"][item["id"]]:
                result["reviews"][item["id"]].update(
                    supported=False, issues=["补充条款改变了原结论的适用条件"],
                )
            # 前面的分片通过不能提前发布；全部补充候选核清后才合并支持性判定。
            assert item.get("review_status") != "current"
            return result

        async def save(_):
            pass

        item["review_status"] = "needs_review"
        assert await audit_combined(flow, review, save)
        assert len(calls) == len(packets)
        assert (item["verification"] == "supported") is not conflict
        assert bool(published_items(flow.state)) is not conflict

    asyncio.run(run())


@pytest.mark.parametrize("omission", [False, True])
def test_partitioned_checks_combine_every_packets_findings_without_mutual_deferral(omission):
    from tender.application.analysis.review import validate

    async def run():
        flow = await flow_fixture(repairs=0)
        first = flow.state["staged_items"][0]
        second = copy.deepcopy(first)
        second["id"] = "second"
        second["business"].update(key="second", title="地点")
        flow.state["staged_items"].append(second)
        flow.entries[0]["record_keys"].append("second")
        first["business"]["content"] = {"内容": "时间条件" * 800}
        second["business"]["content"] = {"内容": "地点条件" * 800}
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=10500)
        calls = []

        async def review(payload):
            calls.append(payload)
            assert all(c["coverage_mode"] == "partition" for c in payload["check_items"])
            result = approve(payload)
            for receipt in result["check_results"].values():
                receipt.update(status="covered_here", issue_indexes=[])
            if omission and len(calls) == 2:
                result["issues"] = [{"topic": "a", "kind": "omission", "action": "read",
                    "target": "地点的变更通知", "detail": "已读原文的变更通知要求未提取",
                    "record_ids": [], "evidence_ids": ["s1r1c0"]}]
                for receipt in result["check_results"].values():
                    receipt.update(status="needs_action", issue_indexes=[0])
            validate(result, payload)
            return result

        async def save(_):
            pass

        assert await audit_combined(flow, review, save)
        assert len(calls) == 2
        assert not flow.data["audit"]["execution_errors"]
        assert bool(flow.data["audit"]["remaining"]) is omission

    asyncio.run(run())


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


def test_repair_issue_keeps_new_comparison_evidence_with_its_record():
    async def run():
        flow = await flow_fixture()
        original = flow.research.seen["s1r1c0"]
        original["chunk_version"] = "2"
        flow.research.seen["s1r1c7"] = original | {
            "block_id": "s1r1c7", "offset": 7, "element_id": 8,
            "content": "专用条款：本项目质保五年。", "chapter": "专用合同条款",
        }
        item = flow.state["staged_items"][0]
        repair = [{"topic": "a", "kind": "conflict", "action": "repair",
                   "issue_id": "b" * 64, "detail": "核对通用与专用期限差异", "target": "质保期限",
                   "record_keys": [item["business"]["key"]], "evidence_ids": ["s1r1c7"]}]
        packets, _ = batches(flow, "a", repair)
        primary, = packets
        assert primary["repair_issues"] == repair
        assert {span["id"] for span in primary["evidence"] + primary["context_evidence"]} == {
            "s1r1c0", "s1r1c7",
        }
        assert "s1r1c7" in primary["record_evidence_ids"][item["id"]]

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
