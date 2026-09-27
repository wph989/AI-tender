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


def database_url() -> str:
    """数据库连接串。

    故意做成函数而不是模块级常量：常量会在 import 时就把值冻结住，
    测试里改了环境变量却拿不到新值——「读一次就定死」的配置是排查噩梦。
    """
    return (
        os.environ.get("DATABASE_URL")
        or _read_env_file(_ENV_FILE).get("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
