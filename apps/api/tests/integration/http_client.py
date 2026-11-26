"""在隔离数据库装配上调用真实HTTP路由，错误断言不再依赖直接调用函数的包装。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tender.api.shared.errors import install_error_handlers


def api_request(request, router, method: str, path: str, *, payload=None):
    app = FastAPI()
    app.state.components = request.app.state.components
    app.include_router(router)
    install_error_handlers(app)
    body = (payload.model_dump(mode="json", exclude_unset=True)
            if isinstance(payload, BaseModel) else payload)
    # 真实请求解析、路由执行和全局错误映射都在此入口发生，连接仍属于既有隔离夹具。
    with TestClient(app) as client:
        return client.request(method, path, json=body)
