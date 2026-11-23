"""详情兼容性必须使用私有协议快照，取消状态不能把现行报告变成旧协议。"""

import copy
from unittest.mock import MagicMock, Mock

import pytest

from tender.application.analysis.service import AnalysisService
from tender.application.shared.errors import Conflict
from tender.domain.analysis.contract import FLOW_VERSION as PROTOCOL_VERSION
from tender.domain.analysis.contract import RUNTIME_VERSION
from tender.ports.repository.analysis.reports import ReportRepository


@pytest.mark.parametrize("protocol,status", [
    (PROTOCOL_VERSION, "running"),
    (PROTOCOL_VERSION, "canceled"),
    (PROTOCOL_VERSION, "completed"),
])
def test_report_compatibility_uses_snapshot_without_exposing_it(
    monkeypatch, protocol, status,
):
    stored = {"id": 42, "project_id": 15, "status": status, "runtime_version": RUNTIME_VERSION,
              "source_snapshot": [], "reference_snapshot": [], "summary": [],
              "category": "goods", "topics": [], "lot_settings": []}
    if protocol is not None:
        stored["skill_snapshot"] = {"__analysis_flow_version__": protocol,
                                    "private_rule": "私有提示词"}
    repository = MagicMock(spec=ReportRepository)
    # 真实仓储每次反序列化新对象，重复读取不能影响保存的协议快照。
    repository.report.side_effect = lambda _: copy.deepcopy(stored)
    repository.report_modules.return_value = []
    repository.report_runs.return_value = []
    repository.collections_for_project.return_value = []
    repository.sources.return_value = []
    repository.execution_active.return_value = False
    service = AnalysisService(repository, 1, Mock(), Mock())
    monkeypatch.setattr(service, "analysis_status", lambda _: {
        "sources": [], "analysis_category": "goods", "analysis_topics": [], "lots": [],
    })

    for _ in range(2):
        result = service.get_report(42)
        assert result["status"] == status
        assert not result["canceling"]
        assert "skill_snapshot" not in result
        assert "私有提示词" not in str(result)


@pytest.mark.parametrize("runtime,protocol", [
    ("legacy", PROTOCOL_VERSION),
    (RUNTIME_VERSION, "research-v2"),
    (RUNTIME_VERSION, None),
])
def test_retired_report_requests_fail_without_reading_report_contents(runtime, protocol):
    repository = MagicMock(spec=ReportRepository)
    repository.report.return_value = {
        "id": 42, "runtime_version": runtime,
        "skill_snapshot": {"__analysis_flow_version__": protocol},
    }
    service = AnalysisService(repository, 1, Mock(), Mock())

    with pytest.raises(Conflict) as error:
        service.get_report(42)

    assert error.value.code == "runtime_retired"
    repository.report_modules.assert_not_called()
    repository.report_runs.assert_not_called()
