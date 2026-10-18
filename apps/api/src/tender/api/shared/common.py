"""路由共享的依赖访问器与请求身份解析。

这里不允许出现数据库查询；路由需要的业务数据统一由服务层提供。
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from tender.config import schema
from tender.config.registry import ConfigRegistry
from tender.ports.documents.converter import OfficeConverter
from tender.ports.jobs.queue import TaskQueue
from tender.ports.storage.blob_store import BlobStore


def engine(request: Request) -> Any:
    return request.app.state.components.engine


def blobs(request: Request) -> BlobStore:
    return request.app.state.components.blobs


def converter(request: Request) -> OfficeConverter:
    return request.app.state.components.converter


def configs(request: Request) -> ConfigRegistry:
    return request.app.state.components.configs


def queue(request: Request) -> TaskQueue:
    return request.app.state.components.queue


def role(request: Request) -> str:
    """角色来自 `x-role` 头（本地单租户部署，默认 admin）；未知角色按最小权限处理。"""
    raw = (request.headers.get("x-role") or "admin").strip().lower()
    return raw if raw in schema.READERS else "viewer"


def actor(request: Request) -> str:
    return (request.headers.get("x-actor") or "local-user")[:200]
