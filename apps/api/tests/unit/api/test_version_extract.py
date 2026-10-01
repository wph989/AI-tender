"""重新抽取端点的请求契约（05 第 3.11 节）。

这里只覆盖不需要数据库的那半条路径：请求体校验、未知字段的错误码、以及
「空列表 = 全部字段类型」的展开口径。查 parse_run、排 job 的那半条要连库才能跑，
由接口清单契约测试（tests/contract/test_api_routes_match_docs.py）与联调验证覆盖，
不在这里伪造一套数据库夹具——那会让测试看起来更全，其实什么都没验证。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tender.api.errors import ApiProblem
from tender.api.parsing import ExtractRequest, _expand_extract_fields
from tender.application.fields import FIELDS


def test_empty_field_keys_expands_to_every_field() -> None:
    """不传字段 = 全部字段：界面上「重跑抽取」不带选择时不至于一条都不跑。"""
    assert _expand_extract_fields(ExtractRequest()) == [field.key for field in FIELDS]


def test_explicit_field_keys_keep_requested_order() -> None:
    requested = [FIELDS[2].key, FIELDS[0].key]
    assert _expand_extract_fields(ExtractRequest(field_keys=requested)) == requested


def test_unknown_field_key_is_rejected() -> None:
    """未知字段必须 400：静默丢掉会让用户以为重跑覆盖了他选的全部字段。"""
    with pytest.raises(ApiProblem) as caught:
        _expand_extract_fields(ExtractRequest(field_keys=["no_such_field"]))
    assert caught.value.status_code == 400
    assert caught.value.code == "invalid_argument"
    assert "no_such_field" in caught.value.message


def test_request_forbids_unknown_keys() -> None:
    """参数名拼错要报错，而不是被忽略后按「全部字段」跑一遍。"""
    with pytest.raises(ValidationError):
        ExtractRequest.model_validate({"field_keys": [], "hint": None, "force": True})
