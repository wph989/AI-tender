"""按版本触发首次解析或管理员重新解析。"""

from __future__ import annotations

from uuid import uuid4

from tender.application.shared.errors import Conflict, InvalidArgument, NotFound
from tender.config.schema import document_execution_snapshot, parse_options
from tender.ports.configuration.registry import ConfigReader
from tender.ports.repository.documents.parsing import ParseRepository
from tender.ports.repository.documents.versions import VersionRepository


class ParseService:
    def __init__(
        self,
        repository: ParseRepository,
        company_id: int,
        configs: ConfigReader,
        versions: VersionRepository,
    ) -> None:
        self.company_id = company_id
        self.configs = configs
        self.versions = versions
        self.repository = repository

    @staticmethod
    def validate(
        *,
        tier: str | None,
        ocr_mode: str | None,
        force: bool,
        reason: str | None,
    ) -> None:
        if tier is not None and tier not in {"flash", "basic", "standard", "advanced"}:
            raise InvalidArgument("tier 不受支持")
        if ocr_mode is not None and ocr_mode not in {"auto", "txt", "ocr"}:
            raise InvalidArgument("ocr_mode 不受支持")
        if force and not (reason and reason.strip()):
            raise InvalidArgument("重新解析必须填写 reason")

    def create_job(
        self,
        version_id: int,
        *,
        tier: str | None,
        ocr_mode: str | None,
        force: bool,
        reason: str | None,
        actor: str,
    ) -> dict[str, object]:
        if self.versions.version(version_id) is None:
            raise NotFound("文档版本不存在")
        # 配置可能走 Redis，先读再开事务，避免在持锁时等待网络。
        active_config = self.configs.active(self.company_id)
        try:
            options = parse_options(
                active_config.resolved if active_config is not None else {},
                tier,
                ocr_mode,
            )
        except ValueError as exc:
            raise InvalidArgument(str(exc)) from exc
        job_id = f"job_{uuid4().hex}"
        with self.repository.transaction() as tx:
            file_row = tx.lock_file(version_id, self.company_id)
            if file_row is None or not file_row["is_parseable"]:
                raise Conflict(
                    "该版本没有可解析的项目文件",
                    code="version_not_parseable",
                )
            if tx.active_job(version_id) is not None:
                raise Conflict(
                    "该版本已有解析任务进行中",
                    code="parse_in_flight",
                    retryable=True,
                )
            if tx.prior_run(version_id) is not None and not force:
                raise Conflict("该版本已有解析结果；如需重建请使用 force", code="parse_exists")
            snapshot = {
                **options,
                "execution": document_execution_snapshot(
                    active_config.resolved if active_config is not None else None
                ),
                "auto_parse": True,
                "trigger": "reparse" if force else "first",
                "reason": reason.strip() if reason else None,
                "actor": actor,
            }
            snapshot_id = tx.snapshot_for_job(active_config)
            tx.insert_job(
                {
                    "id": job_id,
                    "company_id": self.company_id,
                    "project_id": file_row["project_id"],
                    "project_file_id": file_row["project_file_id"],
                    "version_id": version_id,
                    "status": "pending",
                    "stage": "submitting",
                    "progress": {},
                    "config_snapshot": snapshot,
                    "config_snapshot_id": snapshot_id,
                }
            )
        return {
            "job_id": job_id,
            "version_id": version_id,
            "run_id": None,
            "force": force,
            "status": "pending",
        }
