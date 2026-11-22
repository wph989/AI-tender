"""活动配置缓存端口（docs/质量/08-动态配置中心.md）。

配置中心的读路径只依赖这个协议：换成进程内缓存或 Memcached 时，registry 不用改。
实现必须是"尽力而为"的——缓存是加速层，不是事实源，故障时回源数据库而不是把异常抛给调用方。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ConfigCache(Protocol):
    def health(self) -> bool:
        """检查缓存服务当前是否可用，不改变缓存内容。"""
        ...

    def get_active(self, company_id: int) -> Mapping[str, Any] | None:
        """取缓存的活动 release（未命中或缓存不可用时返回 None）。"""
        ...

    def set_active(self, company_id: int, payload: Mapping[str, Any]) -> None:
        """写缓存；实现自行决定 TTL。"""
        ...

    def publish_invalidate(self, company_id: int) -> None:
        """广播失效消息，让其它进程清掉本地缓存。"""
        ...

    def close(self) -> None: ...
