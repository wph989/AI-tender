"""同一天跨重启追加共享分片，用进程间锁保护整条记录和轮转决策。"""

from __future__ import annotations

import errno
import logging
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tender.core.settings import LoggingSettings

if os.name == "nt":
    import msvcrt
else:
    import fcntl

# 清理继续识别旧版时间/PID 和随机标识文件，但追加只选择新的共享分片。
_FILE_NAME = re.compile(
    r"(\d{4}-\d{2}-\d{2})(?:\.(?:\d{2}-\d{2}-\d{2}\.\d+|\d+-[a-f0-9]{12}))?"
    r"\.\d{3,}\.(jsonl|error\.log)\Z"
)
_SHARED_FILE_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})\.(\d{3,})\.(jsonl|error\.log)\Z")


@contextmanager
def _directory_lock(directory: Path):
    # 锁文件不能随分片删除/重建，否则并行进程可能锁住不同文件而同时写入。
    # 每次使用独立句柄，退出后关闭；进程意外退出时由操作系统释放锁。
    with (directory / ".write.lock").open("a+b") as lock:
        deadline = time.monotonic() + 5
        while True:
            try:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待日志写入锁超时") from exc
                time.sleep(0.01)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def emergency_write(text: str) -> None:
    # 不再调用 logging，否则磁盘或格式化故障会递归产生更多日志。
    try:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    except Exception:
        pass


class DailyFileHandler(logging.Handler):
    def __init__(self, options: LoggingSettings, service: str, *, errors: bool = False):
        super().__init__()
        self.options = options
        self.directory = options.directory / service
        self.extension = "error.log" if errors else "jsonl"
        self.timezone = ZoneInfo(options.timezone)
        self._pid = os.getpid()
        self._day: date | None = None
        self._sequence = 0
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

    def _path(self, sequence: int) -> Path:
        return self.directory / f"{self._day}.{sequence:03}.{self.extension}"

    def _append(self, data: bytes) -> None:
        day = self._now().date()
        if self._day != day:
            # 只在初始化/跨天扫描目录；数字序号保证超过 999 后仍选择真正的最新分片。
            self._sequence = max((
                int(match[2]) for path in self.directory.iterdir()
                if (match := _SHARED_FILE_NAME.fullmatch(path.name))
                and match[1] == str(day) and match[3] == self.extension
            ), default=1)
            self._day = day
        # 另一个进程可能已经轮转；持有同一把锁后跟进最新分片，不能继续写旧分片。
        while self._path(self._sequence + 1).exists():
            self._sequence += 1
        while True:
            # 不跨记录保留文件句柄，Windows 清理/重启及 fork 后均无需接管旧句柄。
            with self._path(self._sequence).open("a+b") as stream:
                size = os.fstat(stream.fileno()).st_size
                if size and size + len(data) > self.options.max_file_bytes:
                    self._sequence += 1
                    continue
                if size:
                    # 写入中断可能留下半行甚至半个 UTF-8 字符；保留现场，换片隔离新记录。
                    stream.seek(-1, os.SEEK_END)
                    if stream.read(1) != b"\n":
                        self._sequence += 1
                        continue
                stream.write(data)
                stream.flush()
                return

    def emit(self, record: logging.LogRecord) -> None:
        text = self.format(record)
        try:
            data = (text + "\n").encode("utf-8", errors="backslashreplace")
            self.directory.mkdir(parents=True, exist_ok=True)
            with _directory_lock(self.directory):
                self._append(data)
        except OSError:
            self._warning()
            # 回退的是已脱敏、限长后的记录，不能让 logging 默认错误处理打印原始参数。
            emergency_write(text)

    def cleanup(self) -> None:
        with self.lock:
            today = self._now().date()
            cutoff = date.fromordinal(max(1, today.toordinal() - self.options.retention_days + 1))
            try:
                if not self.directory.exists():
                    return
                # 清理也使用写锁，避免某进程在跨天边界删除另一个进程正在追加的文件。
                with _directory_lock(self.directory):
                    for path in self.directory.iterdir():
                        match = _FILE_NAME.fullmatch(path.name)
                        if (
                            not match or match[2] != self.extension
                            or path.is_symlink() or not path.is_file()
                        ):
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
                                pass
                            except OSError:
                                self._warning()
            except OSError:
                self._warning()

    def close(self) -> None:
        self._stop.set()
        if self._pid == os.getpid() and self._thread is not None:
            self._thread.join(timeout=1)
        super().close()


class SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        emergency_write('{"level":"error","event":"log_stream_unavailable"}')
