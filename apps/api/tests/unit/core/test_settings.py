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


@pytest.fixture(autouse=True)
def _clear_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例都从「环境里没有 DATABASE_URL」开始。

    否则开发机上全局设过这个变量的环境跑测试会得到一个假绿/假红。
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)


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
