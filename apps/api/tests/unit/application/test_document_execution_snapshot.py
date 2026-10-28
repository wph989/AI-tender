"""任务预算在创建时固定，调度参数仍由派发器实时读取。"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from tender.application.documents.parsing import ParseService
from tender.application.knowledge.service import KnowledgeService
from tender.config.schema import document_execution_snapshot, resolve_values
from tender.ports.configuration.registry import ActiveConfig


def test_parse_job_freezes_runtime_values_and_excludes_dispatch_controls():
    created = []
    values = resolve_values({
        "job.timeout.parse_minutes": 7,
        "job.poll.max_attempts": 12,
        "dispatch.interval_seconds": 2,
        "parse.max_inflight": 9,
    })
    active = ActiveConfig(1, 1, {}, values)

    class Repository:
        @contextmanager
        def transaction(self):
            yield SimpleNamespace(
                lock_file=lambda *_: {"is_parseable": True, "project_id": 1, "project_file_id": 2},
                active_job=lambda *_: None,
                prior_run=lambda *_: None,
                snapshot_for_job=lambda _: 3,
                insert_job=created.append,
            )

    service = ParseService(
        Repository(), 1, SimpleNamespace(active=lambda _: active),
        SimpleNamespace(version=lambda _: {"id": 4}),
    )
    service.create_job(4, tier=None, ocr_mode=None, force=False, reason=None, actor="test")
    snapshot = created[0]["config_snapshot"]
    values["job.timeout.parse_minutes"] = 99
    assert snapshot["execution_origin"] == "created"
    assert snapshot["execution"]["job.timeout.parse_minutes"] == 7
    assert snapshot["execution"]["job.poll.max_attempts"] == 12
    assert "dispatch.interval_seconds" not in snapshot["execution"]
    assert "parse.max_inflight" not in snapshot["execution"]


def test_default_runtime_snapshot_is_independent_of_later_defaults():
    first = document_execution_snapshot(None)
    second = document_execution_snapshot(None)
    second["job.timeout.parse_minutes"] = 0
    assert first["job.timeout.parse_minutes"] > 0


@pytest.mark.parametrize("suffix,stage", [("pdf", "probing"), ("docx", "converting")])
@pytest.mark.parametrize("configured", [True, False])
def test_first_source_processing_uses_active_parse_options(suffix, stage, configured):
    created = []
    values = resolve_values({"mineru.tier": "advanced", "mineru.ocr_mode": "ocr"})
    active = ActiveConfig(1, 1, {}, values) if configured else None

    @contextmanager
    def transaction():
        yield SimpleNamespace(
            lock_source=lambda *_: None,
            inflight_source_job=lambda *_: False,
            snapshot_for_job=lambda current: 7 if current is active else None,
            insert_job=created.append,
        )

    store = SimpleNamespace(
        source_for_processing=lambda *_: {
            "id": 2, "project_id": 1, "version_id": None,
            "display_name": "资料." + suffix, "role": "main",
        },
        mark_source_parseable=lambda *_: None,
        transaction=transaction,
    )
    service = KnowledgeService(store, 1, SimpleNamespace(active=lambda _: active), None, None)
    service.process_source(2)
    snapshot = created[0]["config_snapshot"]
    assert created[0]["stage"] == stage
    assert snapshot["tier"] == ("advanced" if configured else "standard")
    assert snapshot["ocr_mode"] == ("ocr" if configured else "auto")
    assert snapshot["execution"] == document_execution_snapshot(values if configured else None)
