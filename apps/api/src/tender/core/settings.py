"""运行时环境配置（部署期参数）。

与 `src/tender/config/`（配置中心）刻意分开：配置中心管的是**业务参数**——存在库里、
页面上能改、改完 5 秒内生效；这里管的是**部署参数**——数据库地址、外部服务地址、密钥，
进程启动前就得定下来。两者来源不同、变更节奏不同，混在一起会出现「改个地址要发版」
或者「重启一次跑掉的业务配置」。

取值优先级（高 → 低）：

1. 真实环境变量——容器 / CI 用它，部署方不必改文件；
2. `apps/api/.env`——本地开发的便利入口，已在 .gitignore 里，不能进版本库；
3. 代码里的默认值——让刚 clone 下来的人能直接 `uv run alembic upgrade head` 试一次。

为什么自己解析 .env 而不引 python-dotenv / pydantic-settings：现在只需要读一个字符串，
多一个依赖就多一份内网离线安装的负担（pyproject 里也写了「依赖随分层落地，不提前装用不上的东西」）。
等部署参数长到需要类型校验与分组（MinIO / LLM / Redis）时再评估换成 pydantic-settings，
那时替换掉的只是本文件的解析部分，调用方 `database_url()` 不变。
"""

from __future__ import annotations

import os
from pathlib import Path

# 本文件在 apps/api/src/tender/core/settings.py，向上四级即 apps/api，.env 与 pyproject 同级。
# 用「源码相对路径」而不是 Path.cwd()：alembic、uvicorn、celery 三种启动方式的 cwd 不同，
# 靠 cwd 找配置会出现「同一个文件在某个进程里读得到、另一个进程里读不到」。
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

# 本地开发默认值；生产环境必须由环境变量或 .env 覆盖。
DEFAULT_DATABASE_URL = "postgresql+psycopg://tender:tender@localhost:5432/tender"
DEFAULT_GOTENBERG_URL = "http://localhost:3000"
# 单次转换的客户端超时（秒）；适配器构造函数里的 180s 只是没给值时的兜底，部署默认值走这里
DEFAULT_GOTENBERG_TIMEOUT_SECONDS = 1800.0
DEFAULT_MINERU_URL = "http://localhost:8000"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_S3_ENDPOINT_URL = "http://localhost:9000"
DEFAULT_S3_BUCKET = "ai-tender"
DEFAULT_S3_REGION = "us-east-1"


def _read_env_file(path: Path) -> dict[str, str]:
    """读取 .env；文件不存在时返回空字典。

    用 utf-8-sig 而不是 utf-8：Windows 记事本保存会加 BOM，带 BOM 时键名会变成
    "\\ufeffDATABASE_URL"，表现为「明明配了却没生效」——这个坑不值得让下一个人再踩。
    """
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        # 空行、注释、没有等号的行一律跳过：手写配置文件里这些是常态，不该直接报错
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(name: str) -> str:
    """按优先级取一个部署参数，返回去空白后的字符串；未配置时返回空串。

    空值一律当作「没写」：compose 里出现 `KEY=` 是常事，让它遮住 .env 会得到
    「明明配了却不生效」——这类问题的排查成本远高于这几行代码。
    """
    raw = os.environ.get(name) or _read_env_file(_ENV_FILE).get(name) or ""
    return raw.strip()


def database_url() -> str:
    """数据库连接串。

    故意做成函数而不是模块级常量：常量会在 import 时就把值冻结住，
    测试里改了环境变量却拿不到新值——「读一次就定死」的配置是排查噩梦。
    """
    return _setting("DATABASE_URL") or DEFAULT_DATABASE_URL


def gotenberg_url() -> str:
    """Gotenberg 基址，末尾不带斜杠（拼路径的地方不再做二次处理）。"""
    return (_setting("GOTENBERG_URL") or DEFAULT_GOTENBERG_URL).rstrip("/")


def gotenberg_credentials() -> tuple[str, str] | None:
    """Gotenberg Basic Auth 凭据；两边都没配时返回 None（本地开发常不带鉴权）。

    只配一边直接报错、不降级为「无鉴权」：静默降级会让一个能转换任意文档的服务
    在内网里对所有人敞开，而这类错误不会有人主动发现。
    同时接受容器风格的名字（GOTENBERG_API_BASIC_AUTH_*）：compose 里就是这两个名字，
    本地照抄容易混，两个都认比让人记住「到底该写哪个」便宜。
    """
    user = _setting("GOTENBERG_USER") or _setting("GOTENBERG_API_BASIC_AUTH_USERNAME")
    password = _setting("GOTENBERG_PASS") or _setting("GOTENBERG_API_BASIC_AUTH_PASSWORD")
    if not user and not password:
        return None
    if not user or not password:
        raise ValueError("Gotenberg 凭据只配了一半：GOTENBERG_USER / GOTENBERG_PASS 必须同时提供")
    return user, password


def gotenberg_timeout_seconds() -> float:
    """单次转换的客户端超时（秒）。

    默认 30 分钟而不是 SDK 常用值 180s：这个预算必须 ≥ 服务端的 API_TIMEOUT（Gotenberg 8 里它就是
    转换的总预算，默认 30s），否则大文档会变成「服务端还在转、客户端已断开」——worker 槽被占着
    却拿不回结果，两边日志对不上（实测数据见 docs/调研/02 第 5 节）。
    """
    raw = _setting("GOTENBERG_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_GOTENBERG_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("GOTENBERG_TIMEOUT_SECONDS 必须是正数") from exc
    if value <= 0:
        raise ValueError("GOTENBERG_TIMEOUT_SECONDS 必须是正数")
    return value


def mineru_url() -> str:
    """MinerU API 基址，统一去掉结尾斜杠以固定路径拼接规则。"""
    return (_setting("MINERU_URL") or DEFAULT_MINERU_URL).rstrip("/")


def mineru_api_key() -> str | None:
    """本地无鉴权开发可留空；生产部署由 MinerU 的 API Key 保护。"""
    return _setting("MINERU_API_KEY") or None


def company_id() -> int:
    """当前单租户部署的公司 ID；集中读取以便后续接入真实租户上下文。"""
    raw = _setting("COMPANY_ID") or "1"
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("COMPANY_ID 必须是正整数") from exc
    if value < 1:
        raise ValueError("COMPANY_ID 必须是正整数")
    return value


def redis_url() -> str:
    """Celery broker；Redis 由部署方提供，不在 API 启动时自动创建队列。"""
    return _setting("REDIS_URL") or DEFAULT_REDIS_URL


def s3_endpoint_url() -> str:
    """MinIO / S3 兼容 API 的内部地址。"""
    return (_setting("S3_ENDPOINT_URL") or DEFAULT_S3_ENDPOINT_URL).rstrip("/")


def s3_access_key() -> str | None:
    return _setting("S3_ACCESS_KEY") or None


def s3_secret_key() -> str | None:
    return _setting("S3_SECRET_KEY") or None


def s3_bucket() -> str:
    return _setting("S3_BUCKET") or DEFAULT_S3_BUCKET


def s3_region() -> str:
    return _setting("S3_REGION") or DEFAULT_S3_REGION


def llm_base_url() -> str | None:
    """内网结构化模型网关；留空时不构造模型客户端。"""
    return _setting("LLM_BASE_URL").rstrip("/") or None


def llm_model() -> str | None:
    return _setting("LLM_MODEL") or None


def llm_api_key() -> str | None:
    return _setting("LLM_API_KEY") or None


def llm_timeout_seconds() -> float:
    raw = _setting("LLM_TIMEOUT_SECONDS") or "90"
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须是正数") from exc
    if value <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须是正数")
    return value


def llm_secret_keys() -> tuple[str, ...]:
    """供应商密钥的加密主密钥：逗号分隔，第一个用于加密，其余用于解密（轮换）。

    未配置时返回空元组而不是抛错：能不能加解密由 core/secrets.py 判断。
    否则「没配主密钥」会让整个进程起不来，而没启用 LLM 管理模块的部署不该被它阻塞。
    """
    raw = _setting("LLM_SECRET_KEYS")
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def mineru_bbox_origin() -> str | None:
    """返回已实测的 MiddleJson bbox 原点；未配置时不生成位置坐标。"""
    value = _setting("MINERU_BBOX_ORIGIN") or "unknown"
    if value not in {"unknown", "top_left", "bottom_left"}:
        raise ValueError("MINERU_BBOX_ORIGIN 必须是 unknown、top_left 或 bottom_left")
    return None if value == "unknown" else value


def mineru_bbox_rotation() -> str | None:
    """返回已实测的旋转坐标语义；未确认时只对 0 度页面写 bbox。"""
    value = _setting("MINERU_BBOX_ROTATION") or "unknown"
    if value not in {"unknown", "visual", "unrotated"}:
        raise ValueError("MINERU_BBOX_ROTATION 必须是 unknown、visual 或 unrotated")
    return None if value == "unknown" else value
