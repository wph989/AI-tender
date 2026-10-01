"""环境配置的取值优先级。

这里盯的是「改了配置却不生效」这类问题：优先级写反、BOM 吃掉键名、空环境变量挡住 .env，
三种都会让运维在错误的库上跑迁移，而命令本身不报错。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from tender.core import settings

_ENV_EXAMPLE = Path(settings.__file__).resolve().parents[3] / ".env.example"


# 本文件要覆盖的全部部署参数。新增一个就读一个：漏清某个变量，
# 开发机上「全局设过它」的测试会话就会得到假绿/假红。
_DEPLOYMENT_ENV_KEYS = (
    "DATABASE_URL",
    "GOTENBERG_URL",
    "GOTENBERG_USER",
    "GOTENBERG_PASS",
    "GOTENBERG_API_BASIC_AUTH_USERNAME",
    "GOTENBERG_API_BASIC_AUTH_PASSWORD",
    "GOTENBERG_TIMEOUT_SECONDS",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_TIMEOUT_SECONDS",
    "LLM_SECRET_KEYS",
)


@pytest.fixture(autouse=True)
def _clear_deployment_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例都从「环境里没有这些变量」开始。"""
    for key in _DEPLOYMENT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _point_at(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(settings, "_ENV_FILE", path)


def test_env_var_wins_over_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql+psycopg://file/db\n", encoding="utf-8")
    _point_at(monkeypatch, env_file)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env/db")

    assert settings.database_url() == "postgresql+psycopg://env/db"


def test_env_file_used_when_env_var_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql+psycopg://file/db\n", encoding="utf-8")
    _point_at(monkeypatch, env_file)

    assert settings.database_url() == "postgresql+psycopg://file/db"


def test_empty_env_var_falls_through_to_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """compose 里写成 `DATABASE_URL=` 是常事，空值应当当作没写，而不是连到空地址上去。"""
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql+psycopg://file/db\n", encoding="utf-8")
    _point_at(monkeypatch, env_file)
    monkeypatch.setenv("DATABASE_URL", "")

    assert settings.database_url() == "postgresql+psycopg://file/db"


def test_default_when_nothing_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")

    assert settings.database_url() == settings.DEFAULT_DATABASE_URL


def test_env_file_tolerates_bom_crlf_quotes_and_comments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows 记事本存 .env 会带 BOM + CRLF；手写时爱加引号和注释。这些都不该让配置失效。"""
    env_file = tmp_path / ".env"
    body = '# 注释\r\n\r\nDATABASE_URL = "postgresql+psycopg://quoted/db"\r\nNOT_A_SETTING\r\n'
    env_file.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    _point_at(monkeypatch, env_file)

    assert settings.database_url() == "postgresql+psycopg://quoted/db"


def test_env_example_is_valid() -> None:
    """仓库里的 .env.example 是给人抄的，抄了不生效等于没有——这里把它的内容真解析一遍。"""
    values = settings._read_env_file(_ENV_EXAMPLE)

    assert "DATABASE_URL" in values, ".env.example 里必须有 DATABASE_URL，否则复制过去等于没配"
    assert "GOTENBERG_URL" in values, "转换服务的地址也要出现在示例里，否则本地跑起来才发现没配"
    assert "GOTENBERG_TIMEOUT_SECONDS" in values, (
        "客户端超时也要进示例：对不上服务端预算就会白转一遍"
    )
    url = make_url(values["DATABASE_URL"])
    assert url.drivername == "postgresql+psycopg", "驱动名拼错会导致 alembic 起来就报 no module"
    assert url.database and url.username


def test_reading_the_real_env_file_does_not_explode() -> None:
    """本机可能根本没有 .env（CI、新 clone）——不能因此报错，也不能返回半解析的结果。"""
    real = Path(settings.__file__).resolve().parents[3] / ".env"
    values = settings._read_env_file(real)
    assert isinstance(values, dict)
    if real.is_file():
        assert all(key and value is not None for key, value in values.items())


def test_no_env_file_defined_outside_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """_ENV_FILE 必须指向 apps/api/.env。

    这条防的是「把 .env 放到仓库根、或按 cwd 找文件」——三种启动方式（alembic / uvicorn / celery）
    的 cwd 不同，靠 cwd 找配置会出现「同一个文件某个进程读得到、另一个读不到」。
    """
    assert Path(settings._ENV_FILE) == Path(settings.__file__).resolve().parents[3] / ".env"
    assert Path(settings._ENV_FILE).parent.name == "api"
    assert os.path.isabs(settings._ENV_FILE)


def test_llm_secret_keys_split_in_order_and_ignore_blanks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """顺序就是轮换顺序：第一个加密、其余解密；空项与空格不能混进密钥列表。"""
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")
    assert settings.llm_secret_keys() == ()

    monkeypatch.setenv("LLM_SECRET_KEYS", " key-one , key-two ,, ")
    assert settings.llm_secret_keys() == ("key-one", "key-two")


def test_env_example_documents_llm_secret_keys() -> None:
    values = settings._read_env_file(_ENV_EXAMPLE)

    assert "LLM_SECRET_KEYS" in values, "保存供应商密钥需要主密钥，示例里必须留位置"


def test_gotenberg_url_default_and_trailing_slash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")
    assert settings.gotenberg_url() == settings.DEFAULT_GOTENBERG_URL

    # 末尾斜杠必须去掉：拼 /forms/... 时会得到双斜杠，反代上可能直接 404
    monkeypatch.setenv("GOTENBERG_URL", "http://gotenberg:3000/")
    assert settings.gotenberg_url() == "http://gotenberg:3000"


def test_gotenberg_credentials_none_when_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")
    assert settings.gotenberg_credentials() is None


def test_gotenberg_credentials_accept_both_naming_styles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")

    monkeypatch.setenv("GOTENBERG_USER", "user")
    monkeypatch.setenv("GOTENBERG_PASS", "pass")
    assert settings.gotenberg_credentials() == ("user", "pass")

    # compose 里用的是容器的变量名，本地照抄容易混——两个都认
    monkeypatch.delenv("GOTENBERG_USER")
    monkeypatch.delenv("GOTENBERG_PASS")
    monkeypatch.setenv("GOTENBERG_API_BASIC_AUTH_USERNAME", "container-user")
    monkeypatch.setenv("GOTENBERG_API_BASIC_AUTH_PASSWORD", "container-pass")
    assert settings.gotenberg_credentials() == ("container-user", "container-pass")


def test_gotenberg_timeout_defaults_to_the_server_side_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """默认值是「大文档能转完」的量级，不是 SDK 常用的 180s。

    600 MB 级标书在同为 LibreOffice 内核的 unoserver 上实测要十几分钟（docs/调研/02 第 5 节）：
    默认值比它小的话，部署方照抄示例就会得到「每份大文档都超时」，而这条路径没有任何启动期提示。
    """
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")
    assert settings.gotenberg_timeout_seconds() == settings.DEFAULT_GOTENBERG_TIMEOUT_SECONDS
    assert settings.gotenberg_timeout_seconds() >= 1800.0


def test_gotenberg_timeout_reads_the_env_and_rejects_non_positive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """0 / 负数 / 非数字一律报错：静默接受会表现成「所有转换都超时」这种最难查的形态。"""
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")

    monkeypatch.setenv("GOTENBERG_TIMEOUT_SECONDS", "2400")
    assert settings.gotenberg_timeout_seconds() == 2400.0

    for bad in ("0", "-1", "30m"):
        monkeypatch.setenv("GOTENBERG_TIMEOUT_SECONDS", bad)
        with pytest.raises(ValueError):
            settings.gotenberg_timeout_seconds()


def test_gotenberg_credentials_half_configured_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """只配一半必须报错：静默降级成「无鉴权」等于把转换服务对全内网敞开。"""
    _point_at(monkeypatch, tmp_path / "does-not-exist.env")
    monkeypatch.setenv("GOTENBERG_USER", "user")

    with pytest.raises(ValueError):
        settings.gotenberg_credentials()
