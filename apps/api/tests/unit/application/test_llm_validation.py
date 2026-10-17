"""管理输入必须在发请求前拒绝，不把凭证或无效能力带入运行时。"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tender.api.errors import install_error_handlers
from tender.api.llm import (
    BindingsRequest,
    FeaturePatch,
    ModelCreate,
    ModelPatch,
    _api_key_for,
    _error_summary,
    router,
)
from tender.application.model_profiles import validate_model
from tender.core.secrets import SecretKeyUnavailable


@pytest.mark.parametrize("value", [0, 1, 10, 11, 1000])
def test_valid_extra_retries(value):
    assert (
        ModelCreate(provider_id=1, model_id="fixture", extra_retries=value).extra_retries == value
    )


@pytest.mark.parametrize("value", [-1, 1.5, True, "1"])
def test_invalid_extra_retries_are_rejected(value):
    with pytest.raises(ValidationError):
        ModelCreate(provider_id=1, model_id="fixture", extra_retries=value)


def test_binding_boolean_id_is_not_coerced_to_model_one():
    with pytest.raises(ValidationError):
        BindingsRequest(model_ids=[True], revision=1)


def test_capability_and_response_parameter_bounds():
    model = ModelCreate(provider_id=1, model_id="fixture").model_dump()
    with pytest.raises(ValueError):
        validate_model("anthropic", model)
    with pytest.raises(ValueError):
        validate_model("openai", model | {"capabilities": ["image_input"]})
    with pytest.raises(ValueError):
        validate_model("openai", model | {"api_mode": "responses", "max_tokens": 8})
    validate_model("openai", model | {"api_mode": "responses", "max_tokens": 16})


def test_database_decimal_temperature_is_accepted():
    # NUMERIC(3,2) 经 psycopg 返回 Decimal；校验必须按数值接受，不能只认 int/float。
    model = ModelCreate(provider_id=1, model_id="fixture").model_dump() | {
        "temperature": Decimal("0.20")
    }
    validate_model("openai_compatible", model)


def test_missing_credential_never_uses_environment_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fixture-env-key")
    with pytest.raises(SecretKeyUnavailable):
        _api_key_for({"auth_mode": "api_key", "api_key_ciphertext": None})
    assert _api_key_for({"auth_mode": "none", "api_key_ciphertext": None}) is None


def test_validation_error_never_echoes_provider_secret():
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/llm/providers",
            json={
                "name": "fixture",
                "base_url": "not-a-url",
                "api_key": "fixture-secret" * 60,
            },
        )
    assert response.status_code == 400
    assert "fixture-secret" not in response.text
    assert '"input"' not in response.text


def test_gateway_error_summary_preserves_details_and_redacts_credentials():
    body = "网关失败 HTTP 504\n<html>网关超时 request_id=upstream-123</html>"
    assert _error_summary(body) == body
    assert "private-key" not in _error_summary(body + "\napi_key=private-key")
    assert _error_summary(None) is None


@pytest.mark.parametrize("model_class", [ModelCreate, ModelPatch])
def test_model_budgets_accept_values_above_old_maximum(model_class):
    fields = {"timeout_seconds": 1200.5, "extra_retries": 99, "max_tokens": 262144}
    if model_class is ModelCreate:
        fields |= {"provider_id": 1, "model_id": "fixture"}
    model = model_class(**fields)
    assert model.max_tokens == 262144
    assert model.timeout_seconds == 1200.5


@pytest.mark.parametrize("value", [float("inf"), float("nan"), 0])
def test_model_timeout_rejects_nonfinite_and_zero(value):
    with pytest.raises(ValidationError):
        ModelPatch(timeout_seconds=value)


def test_feature_budgets_keep_positive_semantics_without_old_maximum():
    payload = FeaturePatch(
        revision=1, failover_limit=10, max_total_requests=1000, deadline_seconds=172800
    )
    assert payload.max_total_requests == 1000
    model = ModelCreate(provider_id=1, model_id="fixture", max_tokens=262144).model_dump()
    selected = validate_model("openai", model)
    assert "max" not in selected["parameter_schema"]["max_tokens"]
    validate_model("openai", model | {"api_mode": "responses"})
    validate_model("gemini", model | {"api_mode": "generate_content", "parameters": {"top_k": 501}})
