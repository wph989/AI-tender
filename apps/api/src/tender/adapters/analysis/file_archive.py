"""原子写入开发复盘档案；独立维护线程按冻结到期时间清理本目录文件。"""

from __future__ import annotations

import atexit
import json
import os
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from tender.core.logging import get_logger
from tender.core.redaction import redact_text

logger = get_logger(__name__)
_NAME = re.compile(
    r"(?P<expires>\d{8}T\d{6}Z)-c\d+-project\d+-report\d+-[a-z][a-z0-9_]*"
    r"-attempt\d+-run\d+(?:\.json|\.[0-9a-f]{32}\.tmp)"
)


def _clean(value):
    # 先清洗字符串再编码JSON，直接清洗序列化文本会破坏错误消息中的转义引号。
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


class FileAnalysisArchive:
    def __init__(self, directory: Path, *, retention_days: int = 1,
                 cleanup_interval_seconds: float = 3600,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        if retention_days < 1 or cleanup_interval_seconds <= 0:
            raise ValueError("分析档案保留天数和清理间隔必须为正数")
        self.directory = directory.resolve()
        self.retention_days, self.interval = retention_days, cleanup_interval_seconds
        self.now = now
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self.cleanup()
            self._stop.clear()
            self._thread = threading.Thread(target=self._maintain, daemon=True,
                                            name="analysis-archive-cleanup")
            self._thread.start()
            atexit.register(self.close)

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _maintain(self) -> None:
        # 闲置Worker也按时清理，不能依赖下一份报告恰好到来；重启时start再补清理。
        while not self._stop.wait(self.interval):
            self.cleanup()

    def write(self, snapshot: dict) -> None:
        meta = snapshot["execution"]
        finished = datetime.fromisoformat(meta["finished_at"])
        if finished.tzinfo is None or meta["status"] not in {
            "completed", "partial", "failed", "canceled",
        }:
            raise ValueError("只归档带明确完成时间的模块终态")
        module = meta["module_key"]
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", module):
            raise ValueError("分析档案的模块标识无效")
        # 到期时间取数据库终态，重复导出不会从当前时间重新开始保留期。
        expires = finished.astimezone(UTC) + timedelta(days=self.retention_days)
        if expires.microsecond:
            expires = (expires + timedelta(seconds=1)).replace(microsecond=0)
        prefix = expires.strftime("%Y%m%dT%H%M%SZ")
        for key in ("company_id", "project_id", "report_id", "attempt", "run_id"):
            if type(meta[key]) is not int or meta[key] < 1:
                raise ValueError("分析档案的执行身份无效：" + key)
        stem = (f"{prefix}-c{meta['company_id']}-project{meta['project_id']}"
                f"-report{meta['report_id']}-{module}-attempt{meta['attempt']}-run{meta['run_id']}")
        self.start()
        if expires <= self.now().astimezone(UTC):
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / (stem + ".json")
        temporary = self.directory / (stem + "." + uuid4().hex + ".tmp")
        value = snapshot | {"expires_at": expires.isoformat(),
                            "retention_days": self.retention_days}
        # 不导出配置或密钥；异常文本仍清洗，诊断副本不能旁路日志的凭证保护。
        content = json.dumps(_clean(value), ensure_ascii=False, indent=2, default=str)
        try:
            temporary.write_text(content + "\n", encoding="utf-8")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def cleanup(self) -> int:
        deleted = 0
        try:
            if not self.directory.exists():
                return 0
            now = self.now().astimezone(UTC)
            for path in self.directory.iterdir():
                match = _NAME.fullmatch(path.name)
                if not match or path.is_symlink() or not path.is_file():
                    continue
                try:
                    expires = datetime.strptime(match["expires"], "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=UTC,
                    )
                    if expires > now:
                        continue
                    # 非递归，只删带本模块完整身份与到期时间的档案及遗留原子写临时文件。
                    path.unlink(missing_ok=True)
                    deleted += 1
                except ValueError:
                    continue
                except OSError:
                    logger.warning("analysis.archive_cleanup_fail", file=path.name)
        except OSError:
            logger.warning("analysis.archive_cleanup_fail", directory=str(self.directory))
        if deleted:
            logger.info("analysis.archive_cleanup_result", deleted_count=deleted)
        return deleted
