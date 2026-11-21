"""补跑携带草稿和核对记录，同attempt恢复保留原预算。"""
import copy
from unittest.mock import Mock

import pytest
from test_analysis_agent_workspace import approve, saved, workspace
from test_analysis_verification_degradation import _RetryStore, _RetryTx

from tender.application.analysis.drafts import resume_workspace
from tender.application.analysis.service import AnalysisService
from tender.application.shared.validation import InputError


@pytest.mark.parametrize("finalized", [False, True])
def test_retry_keeps_drafts_reviews_and_ids_with_fresh_attempt_budget(finalized):
    book = workspace()
    row = saved(book)
    approve(book, row)
    book.state["research"] = {"seen": book.seen, "events": [], "tool_calls": 76}
    book.state["model_unavailable_retries"] = 2
    if finalized:
        book.finalize([row["id"]], "完成")
    previous = copy.deepcopy(book.state)
    tx = _RetryTx([{"id": 9, "status": "partial"}], book.state)
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock(), Mock())
    service.retry_report(3, module_keys=[], mode="resume",
                         max_output_tokens=None, timeout_seconds=None)
    carried = tx.inserted[0]["state"]
    assert carried["research"]["tool_calls"] == 0
    assert carried["staged_items"] == previous["staged_items"]
    assert carried["agent_workspace"]["reviews"] == previous["agent_workspace"]["reviews"]
    assert not carried["agent_workspace"]["finalized"] and "draft" not in carried
    assert "model_unavailable_retries" not in carried
    assert book.state == previous


def test_retry_preserves_notes_and_evidence_without_any_draft():
    book = workspace()
    book.book["notes"] = {"note-1": {"detail": "需补读附件例外"}}
    book.state["research"] = {"seen": book.seen, "events": [], "tool_calls": 20}
    carried = resume_workspace(book.state)
    assert carried["research"]["seen"] == book.seen
    assert carried["research"]["tool_calls"] == 0
    assert carried["agent_workspace"]["notes"] == book.book["notes"]
    assert "agent_progress" not in carried


def test_checkpoint_without_current_workspace_cannot_be_resumed():
    with pytest.raises(InputError, match="旧阶段"):
        resume_workspace({"staged_items": [{"id": "legacy"}]})
