"""供应商密钥的加密与轮换。

cryptography 是 pyproject 里的运行时依赖；本地还没同步锁文件时跳过而不是报错，
保证其余用例仍能给出有效结论。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("cryptography", reason="先执行 uv sync（pyproject 已声明 cryptography）")

from cryptography.fernet import Fernet  # noqa: E402

from tender.core import settings  # noqa: E402
from tender.core.secrets import (  # noqa: E402
    SecretKeyUnavailable,
    decrypt_secret,
    encrypt_secret,
    secret_hint,
)


@pytest.fixture(autouse=True)
def _isolate_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """本机可能真有 apps/api/.env；测试只认自己设的环境变量。"""
    monkeypatch.setattr(settings, "_ENV_FILE", tmp_path / "does-not-exist.env")


def test_round_trip_keeps_plaintext_out_of_ciphertext(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_SECRET_KEYS", Fernet.generate_key().decode())

    token = encrypt_secret("sk-1234567890")

    assert token != "sk-1234567890"
    assert decrypt_secret(token) == "sk-1234567890"


def test_missing_master_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_SECRET_KEYS", raising=False)

    with pytest.raises(SecretKeyUnavailable, match="LLM_SECRET_KEYS"):
        encrypt_secret("sk-x")


def test_rotation_reads_ciphertext_from_previous_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """轮换时新密钥放最前、旧的留在后面，历史密文仍要能读。"""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("LLM_SECRET_KEYS", old_key)
    token = encrypt_secret("sk-rotate")

    monkeypatch.setenv("LLM_SECRET_KEYS", f"{new_key},{old_key}")

    assert decrypt_secret(token) == "sk-rotate"


def test_ciphertext_from_unknown_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_SECRET_KEYS", Fernet.generate_key().decode())
    token = encrypt_secret("sk-lost")

    monkeypatch.setenv("LLM_SECRET_KEYS", Fernet.generate_key().decode())

    with pytest.raises(SecretKeyUnavailable, match="轮换"):
        decrypt_secret(token)


def test_invalid_master_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_SECRET_KEYS", "not-a-fernet-key")

    with pytest.raises(SecretKeyUnavailable):
        encrypt_secret("sk-x")


def test_hint_keeps_only_last_four() -> None:
    assert secret_hint("sk-abcdef") == "****cdef"
    assert secret_hint("abc") == "已配置"
