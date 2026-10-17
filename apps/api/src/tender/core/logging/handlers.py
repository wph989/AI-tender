"""每个进程独立写文件，避免 Windows 文件占用和 prefork 共享轮转句柄。"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from tender.core.settings import LoggingSettings

# 继续识别旧版随机标识文件，升级后历史日志仍需按保留天数清理。
_FILE_NAME = re.compile(
    r"(\d{4}-\d{2}-\d{2})\.(?:\d{2}-\d{2}-\d{2}\.\d+|\d+-[a-f0-9]{12})"
    r"\.\d{3,}\.jsonl\Z"
)


def emergency_write(text: str) -> None:
    # 不再调用 logging，否则磁盘或格式化故障会递归产生更多日志。
    try:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    except Exception:
        pass


class DailyFileHandler(logging.Handler):
    def __init__(self, options: LoggingSettings, service: str):
        super().__init__()
        self.options = options
        self.directory = options.directory / service
        self.timezone = ZoneInfo(options.timezone)
        self._pid = os.getpid()
        self._day: date | None = None
        self._sequence = 0
        self._size = 0
        self._stream = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_warning = float("-inf")

    def _now(self) -> datetime:
        return datetime.now(self.timezone)

    def start(self) -> None:
        self.cleanup()
        self._thread = threading.Thread(
            target=self._maintain, name="tender-log-cleanup", daemon=True
        )
        self._thread.start()

    def _maintain(self) -> None:
        # 独立检查过期日期，不能依赖「恰好有下一条日志」才能清理闲置服务。
        while not self._stop.wait(self.options.cleanup_interval_seconds):
            self.cleanup()

    def _warning(self) -> None:
        now = time.monotonic()
        if now - self._last_warning >= 60:
            self._last_warning = now
            emergency_write('{"level":"error","event":"log_file_unavailable"}')

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                self._warning()
            self._stream = None

    def _open(self, now: datetime) -> None:
        self._close_stream()
        self.directory.mkdir(parents=True, exist_ok=True)
        day = now.date()
        if day != self._day:
            self._day, self._sequence = day, 0
        while self._stream is None:
            self._sequence += 1
            name = f"{now:%Y-%m-%d.%H-%M-%S}.{self._pid}.{self._sequence:03}.jsonl"
            try:
                # 同秒重启或 PID 复用时递增序号，排他创建保证不覆盖历史文件。
                self._stream = (self.directory / name).open("xb")
            except FileExistsError:
                continue
        self._size = 0

    def emit(self, record: logging.LogRecord) -> None:
        text = self.format(record)
        try:
            if self._pid != os.getpid():
                # 即使在 Celery 子进程初始化信号之前出现日志，也不能写入父进程文件。
                self._close_stream()
                self._pid = os.getpid()
                self._day = None
            data = (text + "\n").encode("utf-8", errors="backslashreplace")
            now = self._now()
            if (
                self._stream is None or now.date() != self._day
                or self._size + len(data) > self.options.max_file_bytes
            ):
                self._open(now)
            self._stream.write(data)
            self._stream.flush()
            self._size += len(data)
        except OSError:
            self._close_stream()
            self._warning()
            # 回退的是已脱敏、限长后的记录，不能让 logging 默认错误处理打印原始参数。
            emergency_write(text)

    def cleanup(self) -> None:
        with self.lock:
            today = self._now().date()
            cutoff = date.fromordinal(max(1, today.toordinal() - self.options.retention_days + 1))
            if self._day is not None and self._day < today:
                self._close_stream()
            try:
                if not self.directory.exists():
                    return
                for path in self.directory.iterdir():
                    match = _FILE_NAME.fullmatch(path.name)
                    if not match or path.is_symlink() or not path.is_file():
                        continue
                    try:
                        expired = date.fromisoformat(match[1]) < cutoff
                    except ValueError:
                        continue
                    if expired:
                        try:
                            # 不递归、不按 mtime 猜日期，只删除本模块命名的过期文件。
                            path.unlink()
                        except FileNotFoundError:
                            pass  # 另一个进程已清理同一文件，属于正常竞争。
                        except OSError:
                            self._warning()
            except OSError:
                self._warning()

    def close(self) -> None:
        self._stop.set()
        if self._pid == os.getpid() and self._thread is not None:
            self._thread.join(timeout=1)
        with self.lock:
            self._close_stream()
        super().close()


class SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        emergency_write('{"level":"error","event":"log_stream_unavailable"}')
