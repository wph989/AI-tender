"""配置中心用例：权限、版本状态、门禁与审计编排。

路由只负责解析请求，服务层在这里完成“能否写、何时激活、影响项是否合法”
等判断；真正的 SQL 和锁全部委托给 ``ConfigRepository``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tender.application.shared.errors import (
    Conflict,
    Forbidden,
    InvalidArgument,
    NotFound,
    Unprocessable,
)
from tender.config import gate, schema
from tender.config.gate import ImpactItem
from tender.ports.configuration.registry import ActiveConfig, ConfigReader
from tender.ports.repository.configuration.releases import ConfigRepository, ConfigTransaction

SECRET_MASK = "******"
AUDIT_ACTIONS = frozenset({"create", "acknowledge", "activate", "rollback", "force_activate"})


class ConfigService:
    def __init__(
        self, repository: ConfigRepository, company_id: int, registry: ConfigReader
    ) -> None:
        self.company_id = company_id
        self.registry = registry
        self.repository = repository

    def list_items(self, role: str) -> dict[str, Any]:
        active = self.registry.active(self.company_id)
        overrides = dict(active.values) if active is not None else {}
        items = []
        for entry in schema.ITEMS:
            current = active.resolved[entry.key] if active is not None else entry.default
            items.append(
                {
                    "key": entry.key,
                    "layer": entry.layer,
                    "value_type": entry.value_type,
                    "description": entry.description,
                    "requires_gate": entry.requires_gate,
                    "default": self._mask(entry, entry.default),
                    "value": self._mask(entry, current),
                    "overridden": entry.key in overrides,
                    "writable": role in schema.WRITERS[entry.layer]
                    and entry.key not in schema.READONLY_REASONS,
                    "readonly_reason": schema.READONLY_REASONS.get(entry.key),
                    **schema.value_rules(entry.key),
                }
            )
        return {
            "role": role,
            "items": items,
            "active": (
                None
                if active is None
                else {"release_id": active.release_id, "version_no": active.version_no}
            ),
        }

    def list_releases(self, status: str | None, limit: int) -> dict[str, Any]:
        return {"items": self.repository.list_releases(status, limit)}

    def create_release(
        self,
        *,
        values: dict[str, Any],
        note: str | None,
        based_on: int | None,
        role: str,
        actor: str,
    ) -> dict[str, Any]:
        if not values:
            raise InvalidArgument("没有需要修改的配置项")
        try:
            denial = schema.write_denial(role, values.keys())
        except schema.UnknownConfigKey as exc:
            raise InvalidArgument(str(exc), code="unknown_config_key") from exc
        if denial is not None:
            raise Forbidden(denial)
        for key, value in values.items():
            message = schema.validate_value(key, value)
            if message is not None:
                raise InvalidArgument(message)

        with self.repository.transaction() as transaction:
            transaction.lock_company()
            base_row = (
                self._release(transaction, based_on)
                if based_on is not None
                else transaction.active_release()
            )
            base_values = dict(base_row["values"]) if base_row is not None else {}
            resolved = schema.resolve_values({**base_values, **values})
            message = schema.validate_values(resolved)
            if message is not None:
                raise InvalidArgument(message)
            changed = schema.diff_values(schema.resolve_values(base_values), resolved)
            gated = schema.gated_keys(changed.keys())
            version_no = transaction.next_version_no()
            if not gated:
                transaction.archive_active()
            status = "draft" if gated else "active"
            release_id = transaction.insert_release(
                {
                    "company_id": self.company_id,
                    "version_no": version_no,
                    "values": resolved,
                    "status": status,
                    "based_on": base_row["id"] if base_row is not None else None,
                    "note": note,
                    "created_by": actor,
                }
            )
            self._write_audit(
                transaction,
                release_id=release_id,
                actor=actor,
                action="create",
                diff=changed,
                reason=note,
            )
            if status == "active":
                self._write_audit(
                    transaction,
                    release_id=release_id,
                    actor=actor,
                    action="activate",
                    diff=changed,
                    reason="L1 即时生效（不改变解析与抽取结果）",
                )

        if status == "active":
            self._refresh(release_id, version_no, resolved, resolved)
        return {
            "id": release_id,
            "version_no": version_no,
            "status": status,
            "changed": changed,
            "gated": sorted(gated),
            "note": note,
        }

    def get_release(self, release_id: int) -> dict[str, Any]:
        with self.repository.transaction() as transaction:
            row = self._release(transaction, release_id)
            values = dict(row["values"])
            resolved = schema.resolve_values(values)
            changed = self._changed_against_active(transaction, values)
            impact, acks = self._impact_for(transaction, release_id, values)
            result = gate.evaluate_gate(impact=impact, acknowledged=acks)
            audits = transaction.audit_rows(release_id, 200)
        return {
            "id": row["id"],
            "version_no": row["version_no"],
            "status": row["status"],
            "note": row["note"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "based_on": row["based_on"],
            "overrides": {key: self._mask_stored(key, value) for key, value in values.items()},
            "values": {key: self._mask_stored(key, value) for key, value in resolved.items()},
            "changed": changed,
            "impact": gate.impact_state(impact, acks),
            "gate": result.as_dict(),
            "audit": audits,
        }

    def acknowledge(
        self,
        release_id: int,
        *,
        items: list[tuple[str, str]],
        comment: str | None,
        role: str,
        actor: str,
    ) -> dict[str, Any]:
        if role != "admin":
            raise Forbidden("只有 admin 能确认变更影响清单")
        with self.repository.transaction() as transaction:
            row = self._release(transaction, release_id)
            if row["status"] != "draft":
                raise Conflict("只有 draft 版本需要确认影响清单", code="release_not_draft")
            impact, _ = self._impact_for(transaction, release_id, dict(row["values"]))
            allowed = {(entry.kind, entry.ref) for entry in impact}
            unknown = [
                {"kind": kind, "ref": ref} for kind, ref in items if (kind, ref) not in allowed
            ]
            if unknown:
                raise InvalidArgument(
                    "确认项不在本次变更影响清单里",
                    code="unknown_impact_item",
                    detail={"unknown": unknown},
                )
            transaction.insert_acks(
                release_id=release_id,
                actor=actor,
                items=[ImpactItem(kind, ref) for kind, ref in items],
                comment=comment,
            )
            self._write_audit(
                transaction,
                release_id=release_id,
                actor=actor,
                action="acknowledge",
                diff={"items": [{"kind": kind, "ref": ref} for kind, ref in items]},
                reason=comment,
            )
            impact_state = gate.impact_state(impact, transaction.load_acks(release_id))
        return {
            "id": release_id,
            "acked": [{"kind": kind, "ref": ref} for kind, ref in items],
            "impact": impact_state,
        }

    def activate(
        self,
        release_id: int,
        *,
        force: bool,
        reason: str | None,
        role: str,
        actor: str,
    ) -> dict[str, Any]:
        if role != "admin":
            raise Forbidden("只有 admin 能激活 L2 配置")
        if force and not (reason and reason.strip()):
            raise InvalidArgument("强制激活必须填写理由")
        with self.repository.transaction() as transaction:
            transaction.lock_company()
            row = self._release(transaction, release_id)
            if row["status"] != "draft":
                raise Conflict("只有 draft 版本可以激活", code="release_not_draft")
            values = dict(row["values"])
            impact, acks = self._impact_for(transaction, release_id, values)
            result = gate.evaluate_gate(impact=impact, acknowledged=acks, force=force)
            if not result.passed:
                raise Unprocessable(
                    "配置未通过门禁，不能激活",
                    code="gate_failed",
                    detail={
                        "blockers": list(result.blockers),
                        "soft_breaches": list(result.soft_breaches),
                        "impact": gate.impact_state(impact, acks),
                    },
                )
            changed = self._changed_against_active(transaction, values)
            transaction.archive_active()
            transaction.set_release_status(release_id, "active")
            self._write_audit(
                transaction,
                release_id=release_id,
                actor=actor,
                action="force_activate" if force else "activate",
                diff=changed,
                reason=reason,
            )
            version_no = int(row["version_no"])
            resolved = schema.resolve_values(values)
        self._refresh(release_id, version_no, values, resolved)
        return {
            "id": release_id,
            "status": "active",
            "gate": result.as_dict(),
            "changed": changed,
        }

    def rollback(
        self,
        release_id: int,
        *,
        reason: str | None,
        role: str,
        actor: str,
    ) -> dict[str, Any]:
        if role != "admin":
            raise Forbidden("只有 admin 能回滚配置")
        with self.repository.transaction() as transaction:
            transaction.lock_company()
            target = self._release(transaction, release_id)
            if target["status"] == "draft":
                raise Conflict("draft 版本请先通过门禁再激活", code="release_not_rollbackable")
            if target["status"] == "active":
                raise Conflict("该版本当前就是生效版本", code="already_active")
            current = transaction.active_release()
            target_resolved = schema.resolve_values(dict(target["values"]))
            base = (
                schema.resolve_values(dict(current["values"]))
                if current is not None
                else schema.default_values()
            )
            changed = schema.diff_values(base, target_resolved)
            if current is not None:
                transaction.set_release_status(int(current["id"]), "rolled_back")
            transaction.set_release_status(release_id, "active")
            self._write_audit(
                transaction,
                release_id=release_id,
                actor=actor,
                action="rollback",
                diff=changed,
                reason=reason,
            )
            version_no = int(target["version_no"])
            values = dict(target["values"])
        self._refresh(release_id, version_no, values, target_resolved)
        return {"id": release_id, "status": "active", "changed": changed}

    def list_audit(self, release_id: int | None, limit: int) -> dict[str, Any]:
        return {"items": self.repository.audit_rows(release_id, limit)}

    def _release(self, transaction: ConfigTransaction, release_id: int) -> dict[str, Any]:
        row = transaction.release(release_id)
        if row is None:
            raise NotFound("配置版本不存在")
        return row

    def _changed_against_active(
        self, transaction: ConfigTransaction, values: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        active = transaction.active_release()
        base = schema.resolve_values(dict(active["values"]) if active is not None else {})
        return schema.diff_values(base, schema.resolve_values(values))

    def _impact_for(
        self,
        transaction: ConfigTransaction,
        release_id: int,
        values: Mapping[str, Any],
    ) -> tuple[tuple[ImpactItem, ...], list[tuple[str, str]]]:
        changed = self._changed_against_active(transaction, values)
        impact = gate.build_impact(changed.keys())
        return impact, transaction.load_acks(release_id)

    def _write_audit(
        self,
        transaction: ConfigTransaction,
        *,
        release_id: int,
        actor: str,
        action: str,
        diff: Mapping[str, Any],
        reason: str | None,
    ) -> None:
        if action not in AUDIT_ACTIONS:
            raise ValueError(f"未登记的审计动作：{action}")
        transaction.write_audit(
            release_id=release_id,
            actor=actor,
            action=action,
            diff=diff,
            reason=reason,
        )

    def _refresh(
        self,
        release_id: int,
        version_no: int,
        values: Mapping[str, Any],
        resolved: Mapping[str, Any],
    ) -> None:
        self.registry.refresh(
            self.company_id,
            ActiveConfig(
                release_id=release_id,
                version_no=version_no,
                values=dict(values),
                resolved=dict(resolved),
            ),
        )

    @staticmethod
    def _mask(entry: schema.ConfigItem, value: Any) -> Any:
        return SECRET_MASK if entry.value_type == "secret" else value

    @staticmethod
    def _mask_stored(key: str, value: Any) -> Any:
        entry = schema.ITEMS_BY_KEY.get(key)
        return SECRET_MASK if entry is not None and entry.value_type == "secret" else value
