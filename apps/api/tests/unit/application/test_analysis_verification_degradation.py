"""校验不可用时降级为 partial：只发布已核实成果，未验证条目绝不冒充通过。"""

import copy
from unittest.mock import Mock

from tender.application.analysis.service import AnalysisService
from tender.application.analysis.skills import MODULES
from tender.domain.analysis.contract import RUNTIME_VERSION


class _RetryTx:
    def __init__(self, rows, previous):
        self.rows, self.previous = rows, previous
        self.retry_call = None
        self.pending = None
        self.inserted = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def lock_project(self, project_id):
        pass

    def report_status(self, report_id, lock=False):
        return "partial"

    def execution_active(self, report_id):
        return False

    def try_lock_execution(self, report_id):
        return True

    def other_active_report(self, project_id, report_id):
        return None

    def modules_for_retry(self, report_id, keys):
        self.retry_call = (report_id, keys)
        return self.rows

    def report_has_modules(self, report_id):
        return True

    def mark_modules_pending(self, module_ids):
        self.pending = module_ids

    def module_attempt(self, module_id):
        return 2

    def previous_run_state(self, module_id):
        return copy.deepcopy(self.previous)

    def insert_module_run(self, **kwargs):
        self.inserted.append(kwargs)

    def update_report(self, report_id, values):
        self.report_update = values


class _RetryStore:
    def __init__(self, tx):
        self.tx = tx

    def report(self, report_id):
        return {
            "id": report_id, "project_id": 1, "status": "partial",
            "runtime_version": RUNTIME_VERSION,
            "skill_snapshot": {"__analysis_flow_version__": "skill-agent-v1"},
            "coverage": {"mode": "agent_research"},
        }

    def transaction(self):
        return self.tx

    def resolved_config(self):
        return {}


def test_partial_report_retry_selects_partial_modules():
    from test_analysis_agent_workspace import approve, saved, workspace

    book = workspace()
    approve(book, saved(book))
    previous = copy.deepcopy(book.state)
    tx = _RetryTx([{"id": 9, "status": "partial"}], previous)
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock())
    result = service.retry_report(
        3, module_keys=[], max_output_tokens=None, timeout_seconds=None
    )
    assert result["status"] == "pending"
    assert tx.retry_call == (3, list(MODULES))
    assert tx.pending == [9]
    carried = tx.inserted[0]["state"]
    assert carried["staged_items"] == previous["staged_items"]
    assert carried["agent_workspace"]["reviews"] == previous["agent_workspace"]["reviews"]
    assert not carried["agent_workspace"]["finalized"]
