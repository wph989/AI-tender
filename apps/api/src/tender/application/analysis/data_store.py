"""正式快照的事务发布与按实时权限读取；所有汇总均为确定性处理。"""

from __future__ import annotations

import copy
from collections.abc import Callable

from tender.application.analysis.contract import READABLE_RUNTIMES, RUNTIME_VERSION
from tender.application.analysis.data import (
    DATA_VERSION,
    assemble_dataset,
    data_gap,
    module_records,
)
from tender.application.knowledge.content import fingerprint, source_signature, source_state
from tender.ports.repository.analysis.reports import ReportRepository


def snapshot_manifest(
    status: str, runs: list[dict], modules: list[dict], *, runtime_version: str | None = None,
    inputs: dict | None = None,
) -> str:
    """发布和取数共用指纹；新协议仅在正式业务数据变化时产生新版本。"""
    if inputs is not None:
        # 正文相同也不能让新补遗沿用旧复核；同一份输入下仅运行状态变化则复用。
        return fingerprint([
            2, runtime_version,
            source_signature(inputs["source_snapshot"] + inputs["reference_snapshot"]),
            inputs["category"], inputs["topics"], inputs["lot_settings"], inputs["skill_version"],
            [[m["module_key"], m["business_data"]] for m in modules],
        ])
    if runtime_version == RUNTIME_VERSION:
        # 新运行的状态变化不是正式数据变更；中断重跑应继续保留上一轮同一快照。
        return fingerprint([runtime_version, [
            [m["module_key"], m["business_data"]] for m in modules
        ]])
    return fingerprint([status, runs, [
        [m["module_key"], m["status"], m["business_data"]] for m in modules
    ]])


def unfinished_runs(runs: list[dict]) -> bool:
    # 旧 attempt 的 pending 行可能已被补跑取代，不能永久阻止最新一轮发布。
    latest = {}
    for run in runs:
        previous = latest.get(run["module_id"])
        if previous is None or run["attempt"] > previous["attempt"]:
            latest[run["module_id"]] = run
    return any(r["status"] == "running" for r in runs) or any(
        r["status"] == "pending" for r in latest.values()
    )


def same_frozen_inputs(left: dict, right: dict) -> bool:
    return all(left.get(key) == right.get(key) for key in (
        "runtime_version", "category", "topics", "lot_settings", "skill_version",
    )) and all(source_signature(left[key]) == source_signature(right[key])
               for key in ("source_snapshot", "reference_snapshot"))


def matching_snapshot_state(
    read_state: Callable[[int], dict | None], snapshot: dict,
) -> dict | None:
    # 旧版指纹并未绑定输入；冻结资料也一致时才可使用这次读到的专题成果。
    state = read_state(snapshot["report_id"])
    if state is None:
        return None
    inputs = snapshot["input_snapshot"]
    if (
        state["status"] not in {"waiting", "pending", "running"}
        and not state.get("snapshot_pending")
        and not unfinished_runs(state["runs"])
        and same_frozen_inputs(inputs, state)
        and snapshot_manifest(state["status"], state["runs"], state["modules"],
                              runtime_version=inputs.get("runtime_version"),
                              inputs=state if inputs.get("publication_version") == 2 else None)
        == snapshot["manifest_hash"]
    ):
        return state
    return None


def module_input_signatures(modules: list[dict]) -> dict:
    return {m["module_key"]: (m.get("business_data") or {}).get("quality_input_signature")
            for m in modules}


def snapshot_input_signatures(snapshot: dict, state: dict | None) -> dict:
    inputs = snapshot["input_snapshot"]
    if "module_input_signatures" in inputs:
        return inputs["module_input_signatures"] or {}
    # 历史版本或指纹不匹配时，不能用当前专题的成果给旧结论补签名。
    return module_input_signatures(state["modules"]) if state is not None else {}


def publish_data_snapshot(db: ReportRepository, report_id: int) -> dict | None:
    report = db.report(report_id)
    if report is None:
        return None
    if report["status"] in {"waiting", "pending", "running"}:
        return None
    # 项目会话锁 + 报告行锁串行化并发发布；整段读写在同一个事务里，避免混合版本。
    with db.transaction() as session:
        session.lock_project(report["project_id"])
        locked = session.lock_report(report_id)
        if locked["status"] in {"waiting", "pending", "running"}:
            return None
        clear_pending = {"snapshot_pending": False, "lease_until": None}
        if locked["runtime_version"] not in READABLE_RUNTIMES:
            if locked.get("snapshot_pending"):
                session.update_report(report_id, clear_pending)
            return None
        runs = session.report_runs(report_id)
        if unfinished_runs(runs) and locked["status"] in {"failed", "canceled"}:
            # 若收尾进程已退出，回收孤儿运行；仍持锁的模块退出后再生成快照。
            session.cancel_unlocked_runs(report_id)
            runs = session.report_runs(report_id)
        if unfinished_runs(runs):
            return None
        modules = session.report_modules(report_id)
        digest = snapshot_manifest(locked["status"], runs, modules,
                                   runtime_version=locked["runtime_version"], inputs=locked)
        existing = session.snapshot_by_manifest(report_id, digest)
        if existing and session.latest_snapshot_id(report_id) == existing["id"]:
            session.update_report(report_id, clear_pending)
            return existing
        if locked["runtime_version"] == RUNTIME_VERSION:
            # 升级前已有的快照在输入及正文完全一致时仍可用，避免同一报告平白增加一版。
            legacy_hash = snapshot_manifest(locked["status"], runs, modules,
                                            runtime_version=locked["runtime_version"])
            legacy = session.snapshot_by_manifest(report_id, legacy_hash)
            if (legacy and session.latest_snapshot_id(report_id) == legacy["id"]
                    and same_frozen_inputs(legacy["input_snapshot"], locked)):
                session.update_report(report_id, clear_pending)
                return legacy
        # 同一次发布里标段提取与装配共用一份记录投影，不重复解析业务 JSON。
        records_by_module = {
            module["module_key"]: module_records(module["business_data"]) for module in modules
        }
        lots = []
        derived = set(locked["derived_lot_ids"])
        for module in modules:
            if module["module_key"] != "project_basic_info_parsing":
                continue
            for record in records_by_module[module["module_key"]]:
                if (record["kind"] != "lot" or record.get("verification") != "supported"
                        or record.get("review_status") == "needs_review"):
                    continue
                # 项目目录需要稳定查找键；无原文编号时用已核实名称，分析记录中的 code 仍留空。
                catalog_key = record["code"] or record["title"]
                lot_id = session.lot_id_for_code(locked["project_id"], catalog_key)
                if lot_id is None:
                    lot_id = session.create_lot(
                        locked["project_id"], code=catalog_key, name=record["title"]
                    )
                    derived.add(lot_id)
                item = copy.deepcopy(record) | {"lot_id": lot_id}
                duplicate = next((v for v in lots if v["lot_id"] == lot_id), None)
                if duplicate:
                    duplicate["aliases"] = list(dict.fromkeys([
                        *duplicate["aliases"], record["title"], *record["aliases"],
                    ]))
                    duplicate["citations"].extend(record["citations"])
                else:
                    lots.append(item)
        session.set_derived_lots(report_id, sorted(derived))
        data = assemble_dataset(modules, lots, records_by_module)
        catalog = [c for c in data["coverage"]
                   if c["module_key"] == "project_basic_info_parsing" and c["topic"] == "lots"]
        missing_lots = {lot["id"] for lot in locked["lot_settings"]} - {
            lot["lot_id"] for lot in lots
        }
        catalog_incomplete = any(
            m["module_key"] == "project_basic_info_parsing" and m["status"] != "completed"
            for m in modules
        ) or any(c["status"] not in {"extracted", "not_applicable"} for c in catalog)
        if missing_lots or catalog_incomplete:
            # 一个已识别标段不等于项目只有一个标段，目录缺口期间不能自动选中它。
            data["gaps"].append(data_gap(
                "lot_catalog_unknown", "标段目录尚未核对完整，请确认编制范围",
            ))
            if data["readiness"] == "usable":
                data["readiness"] = "partial"
        for source in locked["source_snapshot"]:
            if source_state(source) != "ready":
                data["gaps"].append(data_gap(
                    "missing_source", "招标材料未完整就绪：" + source.get("file_name", ""),
                ))
                if data["readiness"] == "usable":
                    data["readiness"] = "partial"
        snapshot = session.insert_snapshot(
            report_id=report_id,
            revision=session.next_snapshot_revision(report_id),
            schema_version=DATA_VERSION,
            manifest_hash=digest,
            inputs={k: locked[k] for k in (
                "source_snapshot", "reference_snapshot", "category", "topics", "lot_settings",
                "runtime_version", "skill_version",
            )} | {"publication_version": 2,
                  "module_input_signatures": module_input_signatures(modules)},
            data=data,
        )
        session.update_report(report_id, clear_pending)
        return snapshot


def citations_accessible(resolve: Callable[[dict], dict], citations: list[dict],
                         allowed: list[int], checked: dict[tuple, bool]) -> bool:
    for ref in citations:
        identity = tuple(ref.get(k) for k in (
            "source_id", "collection_id", "project_file_id", "project_id", "version_id",
            "parse_run_id", "element_id", "anchor", "block_id",
        ))
        if identity not in checked:
            try:
                if ref["collection_id"] not in allowed:
                    raise LookupError("资料已解除关联")
                resolve(ref)
                checked[identity] = True
            except LookupError:
                checked[identity] = False
        if not checked[identity]:
            return False
    return True


def accessible_data(
    db: ReportRepository, data: dict, allowed: list[int], *, sources: list[dict] | None = None,
) -> dict:
    """快照存储不可变不代表权限永久有效；读取时整条隐藏失去必要证据的记录。"""
    result = copy.deepcopy(data)
    unavailable = set()
    if sources:
        # gaps 可能只包含缺口说明而没有记录引用，仍需按整份输入快照检查来源撤销。
        live_sources = {s["source_id"] for s in db.sources(allowed)}
        if any(s["source_id"] not in live_sources for s in sources):
            unavailable.add("input_source_unavailable")
    checked: dict[tuple, bool] = {}
    for bucket in ("lots", "facts", "requirements", "format_nodes", "relations", "coverage"):
        visible = []
        for record in result[bucket]:
            if citations_accessible(db.resolve, record.get("citations", []), allowed, checked):
                visible.append(record)
            else:
                unavailable.add(record.get("id") or record["review_id"])
        result[bucket] = visible
    if unavailable:
        # 缺口文本也可能重述撤销资料；此时仅保留访问状态，不泄露历史内容。
        result["gaps"] = [data_gap("source_unavailable", "部分依据已删除或撤销访问，请更新分析")]
        result["quality_issues"] = []
        result["quality_status"] = "unknown"
        result["coverage"] = []
        result["relations"] = [r for r in result["relations"]
                               if r.get("subject_id") not in unavailable
                               and r.get("object_id") not in unavailable]
        result["readiness"] = "unavailable"
    return result
