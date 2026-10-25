"""校验 worker 传给路由的额外重试上限：候选必须收敛，且不改变未超限的配置。"""

from unittest.mock import Mock

import pytest

import tender.application.llm.factory as extraction
from tender.application.llm.routing import ModelCandidate


class _FakeRepository:
    def policy(self, feature_key):
        return None


class _CapturedRouting:
    def __init__(self, feature_key, purpose, candidates, gateway, on_call, **kwargs):
        self.candidates = tuple(candidates)


def _candidate(registry_id: int, extra_retries: int) -> ModelCandidate:
    return ModelCandidate(
        registry_model_id=registry_id,
        provider_id=registry_id,
        display_name=str(registry_id),
        model="fixture",
        base_url="http://gateway",
        api_key=None,
        timeout=30,
        temperature=None,
        max_tokens=None,
        extra_retries=extra_retries,
    )


@pytest.mark.parametrize(
    "limit,expected", [(2, [2, 1]), (None, [5, 1])]
)
def test_extra_retries_limit_only_lowers_configured_retries(monkeypatch, limit, expected):
    factory = extraction.RoutingModelFactory(_FakeRepository(), Mock(), Mock())
    monkeypatch.setattr(
        factory,
        "_load_candidates",
        lambda feature_key, purpose: [_candidate(1, 5), _candidate(2, 1)],
    )
    monkeypatch.setattr(extraction, "RoutingModel", _CapturedRouting)
    model = factory("analysis", "analysis", extra_retries_limit=limit)
    assert [candidate.extra_retries for candidate in model.candidates] == expected
