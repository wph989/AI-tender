"""任务互斥契约；调用方只判断是否获得执行权，不接触数据库连接。"""

from contextlib import AbstractContextManager
from typing import Protocol


class TaskLocks(Protocol):
    def lock(self, key: str, *, wait: bool = False) -> AbstractContextManager[bool]: ...
