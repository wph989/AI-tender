# 后端镜像：API / migrate / worker / beat 共用，角色由 compose 的 command 区分。
# 构建上下文是 apps/api，所以下面的路径都相对该目录。

# uv 只借二进制，版本对齐开发机；离线环境换成内部 registry 里的同版本镜像
# 依赖下载同理：内网用 UV_DEFAULT_INDEX 指向私服（构建期需要能访问 PyPI 或私服）
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.24 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    # 容器里不需要 .venv：直接装进系统解释器，uvicorn / celery / alembic 都在 PATH 上
    UV_PROJECT_ENVIRONMENT=/usr/local

# curl 供 compose 健康检查；libstdc++6 是 pypdfium2 自带 libpdfium 的运行期依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖、再拷源码：改业务代码不会让依赖层缓存失效
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 迁移文件必须进镜像：DDL 的事实源是设计文档，可执行副本是这些迁移（见 docs/工程/10 第 4.5 节）
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# 非 root 运行；只 chown 应用目录，不动系统路径
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# 默认角色是 API；worker / beat / migrate 在 compose 里覆盖 command
CMD ["uvicorn", "tender.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]