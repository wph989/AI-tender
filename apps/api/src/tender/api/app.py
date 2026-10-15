"""FastAPI 装配点；第三方连接只在这里创建并在进程退出时关闭。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from tender.api import (
    config,
    jobs,
    knowledge,
    llm,
    parsing,
    project_files,
    projects,
    versions,
)
from tender.api.errors import install_error_handlers
from tender.core.di import ApiComponents, create_api_components


def create_app(components: ApiComponents | None = None) -> FastAPI:
    runtime = components or create_api_components()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await runtime.aclose()

    app = FastAPI(title="AI-Tender API", version="0.1.0", lifespan=lifespan)
    app.state.components = runtime
    install_error_handlers(app)
    router = APIRouter(prefix="/api/v1")

    @router.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(projects.router)
    app.include_router(project_files.router)
    app.include_router(versions.router)
    app.include_router(parsing.router)
    app.include_router(jobs.router)
    app.include_router(llm.router)
    app.include_router(config.router)
    app.include_router(knowledge.router)
    return app


app = create_app()
