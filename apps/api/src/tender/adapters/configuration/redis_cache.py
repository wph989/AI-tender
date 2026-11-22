"""Redis 活动配置缓存：key `config:active:{company_id}` + TTL 60 秒兜底。

读取策略见 docs/质量/08-动态配置中心.md。

Redis 在这里只是缓存，不是事实源：连接失败或 pub/sub 丢消息都只降级成"多回源几次数据库"，
所以所有操作都吞掉异常并记日志——把读配置做成会因为 Redis 抖动而 500 的接口，
比"60 秒后才一致"更糟。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from tender.core import settings

CACHE_KEY_TEMPLATE = "config:active:{company_id}"
INVALIDATE_CHANNEL = "config:invalidate"
DEFAULT_TTL_SECONDS = 60

logger = logging.getLogger(__name__)


def _key(company_id: int) -> str:
    return CACHE_KEY_TEMPLATE.format(company_id=company_id)


class RedisConfigCache:
    def __init__(
        self,
        url: str | None = None,
        *,
        client: Any | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        # client 可注入：单测不该为了验证序列化逻辑去起一个 Redis。
        self._client = (
            client if client is not None else redis.Redis.from_url(
                url or settings.redis_url(),
                # 缓存故障必须快速回源，不能让半开连接或客户端默认重试拖住业务请求。
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                retry=Retry(NoBackoff(), 0),
            )
        )
        self._ttl_seconds = ttl_seconds

    def get_active(self, company_id: int) -> Mapping[str, Any] | None:
        try:
            raw = self._client.get(_key(company_id))
        except Exception as exc:
            logger.warning("Redis 读配置缓存失败，回源数据库：%s", exc)
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            logger.warning("配置缓存内容不是合法 JSON，按未命中处理")
            return None
        return payload if isinstance(payload, dict) else None

    def set_active(self, company_id: int, payload: Mapping[str, Any]) -> None:
        try:
            self._client.set(
                _key(company_id),
                json.dumps(dict(payload), ensure_ascii=False),
                ex=self._ttl_seconds,
            )
        except Exception as exc:
            logger.warning("Redis 写配置缓存失败，只影响生效速度：%s", exc)

    def publish_invalidate(self, company_id: int) -> None:
        try:
            self._client.publish(INVALIDATE_CHANNEL, str(company_id))
        except Exception as exc:
            logger.warning("配置失效消息发送失败，等 TTL 兜底：%s", exc)

    def health(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception as exc:
            logger.warning("Redis 健康检查失败：%s", exc)
            return False

    def close(self) -> None:
        try:
            self._client.close()
        except Exception as exc:
            logger.warning("关闭 Redis 连接失败：%s", exc)
