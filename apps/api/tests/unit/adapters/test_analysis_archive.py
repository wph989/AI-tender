"""复盘档案的保留期、原子写、闲置清理和清理范围。"""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from tender.adapters.analysis.file_archive import FileAnalysisArchive
from tender.core import settings

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def snapshot(**meta):
    return {"execution": {
        "company_id": 1, "project_id": 2, "report_id": 3,
        "module_key": "project_basic_info_parsing", "run_id": 4, "attempt": 1,
        "status": "completed", "started_at": (NOW - timedelta(days=3)).isoformat(),
        "finished_at": NOW.isoformat(), **meta,
    }, "research": {"seen": {"s1r1c0": {"content": "项目预算三万元"}}}}


def test_default_retention_is_one_day_after_completion_not_after_start_or_last_write(tmp_path):
    clock = [NOW + timedelta(hours=23)]
    archive = FileAnalysisArchive(tmp_path, now=lambda: clock[0])
    try:
        archive.write(snapshot())
        path = next(tmp_path.glob("*.json"))
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["retention_days"] == 1
        assert value["research"]["seen"]["s1r1c0"]["content"] == "项目预算三万元"
        assert archive.cleanup() == 0
        archive.write(snapshot())
        assert list(tmp_path.glob("*.json")) == [path]
        assert value["expires_at"] == json.loads(path.read_text(encoding="utf-8"))["expires_at"]
        clock[0] = NOW + timedelta(days=1)
        assert archive.cleanup() == 1 and not path.exists()
    finally:
        archive.close()


def test_idle_worker_and_startup_clean_expired_archives_without_new_analysis(tmp_path):
    clock = [NOW]
    archive = FileAnalysisArchive(tmp_path, cleanup_interval_seconds=0.01, now=lambda: clock[0])
    try:
        archive.write(snapshot())
        path = next(tmp_path.glob("*.json"))
        clock[0] = NOW + timedelta(days=2)
        deadline = time.monotonic() + 2
        while path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not path.exists()
        archive.close()
        clock[0] = NOW
        archive.write(snapshot())
        archive.close()
        clock[0] = NOW + timedelta(days=2)
        archive.start()
        assert not list(tmp_path.glob("*.json"))
    finally:
        archive.close()


def test_cleanup_preserves_other_documents_directories_and_unexpired_archives(tmp_path):
    archive = FileAnalysisArchive(tmp_path, now=lambda: NOW)
    try:
        archive.write(snapshot())
        target = next(tmp_path.glob("*.json"))
        unrelated = tmp_path / "notes.json"
        unrelated.write_text("开发者反馈", encoding="utf-8")
        nested = tmp_path / "20200101T000000Z-c1-project1-report1-module-attempt1-run1.json"
        nested.mkdir()
        # 崩溃遗留的原子写临时文件也沿用同一到期时间，不递归删除其它开发资料。
        temporary = target.with_name(target.stem.replace("20261109", "20261107")
                                    + "." + "a" * 32 + ".tmp")
        temporary.write_text("未完成写入", encoding="utf-8")
        assert archive.cleanup() == 1
        assert target.exists() and unrelated.exists() and nested.is_dir()
    finally:
        archive.close()


def test_in_progress_and_expired_replay_do_not_create_live_archive(tmp_path):
    archive = FileAnalysisArchive(tmp_path, now=lambda: NOW)
    try:
        with pytest.raises(ValueError):
            archive.write(snapshot(status="running"))
        archive.write(snapshot(finished_at=(NOW - timedelta(days=2)).isoformat()))
        assert not list(tmp_path.glob("*.json"))
    finally:
        archive.close()


def test_archive_configuration_default_and_environment_override(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    for key in ("ANALYSIS_ARCHIVE_DIR", "ANALYSIS_ARCHIVE_RETENTION_DAYS",
                "ANALYSIS_ARCHIVE_CLEANUP_INTERVAL_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    value = settings.analysis_archive_settings()
    assert value.retention_days == 1 and value.directory == tmp_path / "logs" / "analysis"
    monkeypatch.setenv("ANALYSIS_ARCHIVE_RETENTION_DAYS", "3")
    monkeypatch.setenv("ANALYSIS_ARCHIVE_CLEANUP_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("ANALYSIS_ARCHIVE_DIR", str(tmp_path / "debug"))
    value = settings.analysis_archive_settings()
    assert value.retention_days == 3 and value.cleanup_interval_seconds == 60
    assert value.directory == tmp_path / "debug"
    monkeypatch.setenv("ANALYSIS_ARCHIVE_RETENTION_DAYS", "0")
    with pytest.raises(ValueError):
        settings.analysis_archive_settings()


def test_quoted_error_credentials_are_redacted_without_corrupting_json(tmp_path):
    archive = FileAnalysisArchive(tmp_path, now=lambda: NOW)
    try:
        archive.write(snapshot(error='api_key="secret-value"; password=another-secret'))
        text = next(tmp_path.glob("*.json")).read_text(encoding="utf-8")
        value = json.loads(text)
        assert "secret-value" not in text and "another-secret" not in text
        assert "已隐藏" in value["execution"]["error"]
    finally:
        archive.close()
