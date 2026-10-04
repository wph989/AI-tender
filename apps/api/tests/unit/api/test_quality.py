"""覆盖有复核记录时的统计响应，防止只在空库上正常的接口进入前端。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tender.api.quality import router


@pytest.mark.parametrize("mode", ["item", "batch", "spot_check"])
def test_field_stats_keeps_review_mode_separate_from_counts(mode):
    # 这里只隔离数据库取数；经 HTTP 路由验证字符串维度、指标转换和三档响应。
    attempts = Mock()
    attempts.mappings.return_value.all.return_value = [
        {"field_key": "budget_amount", "review_mode": mode,
         "attempt_no": 1, "action": "confirm", "n": 2},
        {"field_key": "budget_amount", "review_mode": mode,
         "attempt_no": 1, "action": "reject", "n": 1},
    ]
    instances = Mock()
    instances.mappings.return_value.all.return_value = [{
        "field_key": "budget_amount", "review_mode": mode, "reviewed": 3,
        "cum_1_total": 3, "cum_1_pass": 2,
        "cum_2_total": 3, "cum_2_pass": 2,
        "cum_3_total": 3, "cum_3_pass": 2,
    }]
    manual = Mock()
    manual.mappings.return_value.all.return_value = [
        {"field_key": "budget_amount", "reviewed": 3, "manual": 1},
    ]
    evidence = Mock()
    evidence.mappings.return_value.one.return_value = {
        "total": 3, "bbox_missing": 0, "anchor_missing": 0,
    }
    database = MagicMock()
    database.connect.return_value.__enter__.return_value.execute.side_effect = [
        attempts, instances, manual, evidence,
    ]
    registry = Mock()
    registry.resolved.return_value = {
        "extract.rerun.hide_threshold": 0.1, "extract.rerun.min_sample": 30,
    }
    app = FastAPI()
    app.include_router(router)
    app.state.components = SimpleNamespace(engine=database, configs=registry)

    with TestClient(app) as client:
        response = client.get("/api/v1/stats/fields?scope=all&window=90d")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["field_key"] == "budget_amount"
    assert item["by_mode"][mode]["reviewed_instances"] == 3
    assert item["by_mode"][mode]["first_pass_rate"] == 0.6667
    assert item["by_mode"][mode]["cumulative_pass"] == {"1": 0.6667, "2": 0.6667, "3": 0.6667}
    assert item["reviewed"] == (3 if mode == "item" else 0)
    assert item["manual_fallback_rate"] == 0.3333
