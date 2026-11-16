"""详情兼容性必须使用私有协议快照，取消状态不能把现行报告变成旧协议。"""

import copy
from unittest.mock import MagicMock, Mock

import pytest

from tender.application.analysis.contract import FLOW_VERSION as PROTOCOL_VERSION
from tender.application.analysis.contract import READABLE_RUNTIMES, RUNTIME_VERSION
from tender.application.analysis.service import AnalysisService
from tender.ports.repository.analysis.reports import ReportRepository


@pytest.mark.parametrize("runtime,protocol,status,compatible", [
    (RUNTIME_VERSION, PROTOCOL_VERSION, "running", True),
    (RUNTIME_VERSION, PROTOCOL_VERSION, "canceled", True),
    (RUNTIME_VERSION, PROTOCOL_VERSION, "completed", True),
    (RUNTIME_VERSION, "research-v2", "canceled", False),
    (RUNTIME_VERSION, None, "canceled", False),
    ("legacy", PROTOCOL_VERSION, "canceled", False),
    ("deepagents-0.7.22-v5-records", "research-v3", "completed", False),
])
def test_report_compatibility_uses_snapshot_without_exposing_it(
    monkeypatch, runtime, protocol, status, compatible,
):
    stored = {"id": 42, "project_id": 15, "status": status, "runtime_version": runtime,
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
    service = AnalysisService(repository, 1, Mock(), Mock(), Mock())
    monkeypatch.setattr(service, "analysis_status", lambda _: {
        "sources": [], "analysis_category": "goods", "analysis_topics": [], "lots": [],
    })

    for _ in range(2):
        result = service.get_report(42)
        assert result["execution_compatible"] is compatible
        assert result["runtime_retired"] is (runtime not in READABLE_RUNTIMES)
        assert result["status"] == status
        assert not result["canceling"]
        assert "skill_snapshot" not in result
        assert "私有提示词" not in str(result)
