"""供应商密钥的加密存储：Fernet 对称加密 + 多密钥轮换。

为什么密钥不直接明文入库（见 docs/设计/12 第 5 节）：
- 数据库备份、只读副本、运维导出都可能把整库带走，明文密钥会被一并带走；
- 主密钥放在进程环境变量里，泄露一份数据库不等于泄露密钥。

为什么用 Fernet 而不是自己拼 AES：Fernet 把「加密 + 完整性校验 + 版本头」封在一个
不可变格式里，`cryptography` 又是维护活跃、审计充分的实现；自研加密没有任何收益。

轮换方式：`LLM_SECRET_KEYS` 逗号分隔，第一个用于加密新值，其余依次尝试解密旧值。
换密钥时把新密钥放到最前面、旧的留在后面，历史密文仍然能读；确认全部轮换完再删旧密钥。
"""

from __future__ import annotations

from typing import Any

from tender.core import settings


class SecretKeyUnavailable(RuntimeError):
    """没有可用的主密钥、依赖缺失，或密文无法用任何已配置密钥解开。

    调用方把它翻译成 ``secret_key_unavailable``（HTTP 503），见 api/errors.py。
    这里不抛领域错误：core 是纯工具层，不认识 HTTP 与业务错误码。
    """


def _fernet() -> tuple[Any, Any]:
    """延迟导入 cryptography。

    没装依赖时服务仍要能启动：密钥加解密是管理页的一个功能，
    不该让解析、复核这些不相关的接口一起 500。真正用到时再给明确报错。
    """
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ModuleNotFoundError as exc:  # pragma: no cover - 部署缺依赖时的兜底
        raise SecretKeyUnavailable(
            "未安装 cryptography，无法保存或读取供应商密钥（在 apps/api 执行 uv add cryptography）"
        ) from exc
    return Fernet, InvalidToken


def _cipher() -> Any:
    keys = settings.llm_secret_keys()
    if not keys:
        raise SecretKeyUnavailable("未配置 LLM_SECRET_KEYS，无法保存或读取供应商密钥")
    fernet, _ = _fernet()
    try:
        return fernet(keys[0].encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise SecretKeyUnavailable("LLM_SECRET_KEYS 第一项不是合法的 Fernet 密钥") from exc


def encrypt_secret(plaintext: str) -> str:
    """加密并返回可直接入库的 ASCII 密文。"""
    return _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """按 LLM_SECRET_KEYS 的顺序尝试解密，支持密钥轮换期的新旧混用。"""
    keys = settings.llm_secret_keys()
    if not keys:
        raise SecretKeyUnavailable("未配置 LLM_SECRET_KEYS，无法读取供应商密钥")
    fernet, invalid_token = _fernet()
    for key in keys:
        try:
            return fernet(key.encode("ascii")).decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (invalid_token, ValueError, TypeError):
            continue
    raise SecretKeyUnavailable("密文无法用已配置的 LLM_SECRET_KEYS 解开，检查是否漏了轮换前的密钥")


def secret_hint(plaintext: str) -> str:
    """只保留末 4 位供页面辨认；短于 4 位时全部隐藏。"""
    return f"****{plaintext[-4:]}" if len(plaintext) > 4 else "已配置"


def secret_key_ready() -> bool:
    """只报告能否加密，避免把部署主密钥或错误详情送到浏览器。"""
    try:
        _cipher()
        return True
    except SecretKeyUnavailable:
        return False
