"""验证日志的运行行为：跨天、保留边界、并发隔离和真实框架入口。"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
import structlog
from celery import Celery
from fastapi import FastAPI, Query, Request
from starlette.responses import StreamingResponse

from tender.api.errors import install_error_handlers
from tender.api.logging import RequestLoggingMiddleware, _AccessLogWindow, throttle_access_log
from tender.core import logging as runtime
from tender.core import settings
from tender.core.logging import bind_context, configure_logging, get_context, get_logger
from tender.core.logging import setup as logging_setup
from tender.core.logging.formatters import MAX_RECORD_BYTES, make_formatter
from tender.core.logging.handlers import DailyFileHandler


@pytest.fixture
def options(monkeypatch, tmp_path):
    previous = logging_setup._configured
    old_structlog = structlog.get_config()
    root_level = logging.getLogger().level
    logger_states = {
        name: (item.level, item.disabled, item.propagate, list(item.handlers), list(item.filters))
        for name, item in logging.Logger.manager.loggerDict.items()
        if isinstance(item, logging.Logger)
    }
    runtime.shutdown_logging()
    runtime.clear_context()
    monkeypatch.setattr(settings, "_ENV_FILE", tmp_path / ".env")
    for key in (
        "LOG_LEVEL", "LOG_OUTPUT", "LOG_CONSOLE_FORMAT", "LOG_DIR", "LOG_RETENTION_DAYS",
        "LOG_MAX_FILE_BYTES", "LOG_TIMEZONE", "LOG_CLEANUP_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    value = settings.LoggingSettings(directory=tmp_path / "logs", output="file")
    yield value
    runtime.shutdown_logging()
    runtime.clear_context()
    if previous:
        configure_logging(previous[1], previous[2])
    else:
        structlog.configure(**old_structlog)
    logging.getLogger().setLevel(root_level)
    for name, (level, disabled, propagate, handlers, filters) in logger_states.items():
        item = logging.getLogger(name)
        item.setLevel(level)
        item.disabled, item.propagate = disabled, propagate
        item.handlers, item.filters = handlers, filters


def read_logs(directory: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(directory.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def record(message="中文日志"):
    return logging.LogRecord("tender.test", logging.INFO, __file__, 1, message, (), None)


def test_daily_and_size_rotation_preserve_whole_utf8_records(options, monkeypatch):
    handler = DailyFileHandler(replace(options, max_file_bytes=500), "worker")
    handler.setFormatter(make_formatter("worker", json_output=True))
    now = [datetime(2026, 10, 17, 23, 59, tzinfo=ZoneInfo("Asia/Singapore"))]
    monkeypatch.setattr(handler, "_now", lambda: now[0])
    try:
        for index in range(6):
            handler.handle(record(f"第 {index} 条中文日志"))
        now[0] = datetime(2026, 10, 18, 0, 0, tzinfo=now[0].tzinfo)
        handler.handle(record("跨天"))
    finally:
        handler.close()
    paths = sorted((options.directory / "worker").glob("*.jsonl"))
    assert len(paths) > 2
    assert all(path.stat().st_size <= 500 for path in paths)
    assert paths[-1].name == f"2026-10-18.00-00-00.{os.getpid()}.001.jsonl"
    assert all(
        path.name.startswith(f"2026-10-17.23-59-00.{os.getpid()}.") for path in paths[:-1]
    )
    logs = read_logs(options.directory)
    assert len(logs) == 7
    assert logs[-1]["event"] == "跨天"


@pytest.mark.parametrize("identity", ["42-abcdef123456", "21-42-03.42"])
def test_retention_counts_days_not_files_and_skips_unmanaged_files(options, monkeypatch, identity):
    handler = DailyFileHandler(options, "api")
    monkeypatch.setattr(
        handler, "_now", lambda: datetime(2026, 10, 17, tzinfo=ZoneInfo("Asia/Singapore"))
    )
    directory = options.directory / "api"
    directory.mkdir(parents=True)
    # 30 天包含当天：9 月 18 日仍保留；9 月 17 日所有分片都已过期。
    for day in ("2026-09-17", "2026-09-18", "2026-10-17"):
        for part in range(1, 40):
            (directory / f"{day}.{identity}.{part:03}.jsonl").write_text(
                "{}\n", encoding="utf-8"
            )
    unrelated = directory / "2020-01-01.backup.jsonl"
    unrelated.write_text("保留", encoding="utf-8")
    handler.cleanup()
    handler.close()
    assert not list(directory.glob("2026-09-17.*"))
    assert len(list(directory.glob("2026-09-18.*"))) == 39
    assert len(list(directory.glob("2026-10-17.*"))) == 39
    assert unrelated.read_text(encoding="utf-8") == "保留"


def test_idle_cleanup_and_shutdown_without_emitting(options, monkeypatch):
    handler = DailyFileHandler(replace(options, cleanup_interval_seconds=0.01), "api")
    called = threading.Event()
    counts = []
    original = handler.cleanup

    def cleanup():
        original()
        counts.append(1)
        if len(counts) >= 2:
            called.set()

    monkeypatch.setattr(handler, "cleanup", cleanup)
    handler.start()
    try:
        assert called.wait(2), "没有日志写入时也必须定时清理"
    finally:
        handler.close()
    assert not handler._thread.is_alive()
    assert not options.directory.exists(), "没有记录时不应生成空日志"


def test_cleanup_retries_locked_files_and_ignores_concurrent_deletion(options, monkeypatch, capsys):
    handler = DailyFileHandler(options, "api")
    directory = options.directory / "api"
    directory.mkdir(parents=True)
    path = directory / "2000-01-01.42-abcdef123456.001.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    original = Path.unlink
    with monkeypatch.context() as local:
        def locked(candidate):
            raise PermissionError("文件暂被占用")
        local.setattr(Path, "unlink", locked)
        handler.cleanup()
    assert path.exists()
    assert "log_file_unavailable" in capsys.readouterr().err
    handler.cleanup()
    assert not path.exists()
    path.write_text("{}\n", encoding="utf-8")
    with monkeypatch.context() as local:
        def already_removed(candidate):
            original(candidate)
            raise FileNotFoundError
        local.setattr(Path, "unlink", already_removed)
        handler._last_warning = float("-inf")
        handler.cleanup()
    assert not path.exists()
    assert capsys.readouterr().err == ""
    handler.close()


def test_restarts_do_not_overwrite_and_initialization_is_idempotent(options, monkeypatch):
    # 固定同一秒和同一 PID，验证新命名发生冲突时仍能保留两次初始化产生的记录。
    now = datetime(2026, 10, 17, 21, 42, 3, tzinfo=ZoneInfo("Asia/Singapore"))
    monkeypatch.setattr(DailyFileHandler, "_now", lambda self: now)
    configure_logging("api", options)
    configure_logging("api", options)
    logging.getLogger("tender.standard").info("标准 logging", extra={"job_id": 123})
    runtime.shutdown_logging()
    configure_logging("api", options)
    get_logger("tender.structured").info("structured_event", report_id=456)
    logs = read_logs(options.directory)
    assert len(logs) == 2
    assert {path.name for path in (options.directory / "api").glob("*.jsonl")} == {
        f"2026-10-17.21-42-03.{os.getpid()}.{part:03}.jsonl" for part in (1, 2)
    }
    assert logs[0]["service"] == logs[1]["service"] == "api"
    assert {log["event"] for log in logs} == {"标准 logging", "structured_event"}
    assert any(log.get("job_id") == 123 for log in logs)


def test_nested_context_and_threads_do_not_leak(options):
    configure_logging("worker", options)
    barrier = threading.Barrier(4)

    def work(index):
        assert get_context() == {}
        with bind_context(request_id=f"request-{index}"):
            barrier.wait()
            with bind_context(job_id=index):
                get_logger("tender.test").info("thread_event")
            assert get_context() == {"request_id": f"request-{index}"}
        assert get_context() == {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, range(4)))
    logs = read_logs(options.directory)
    assert len(logs) == 4
    assert all(log["request_id"] == f"request-{log['job_id']}" for log in logs)


def test_redaction_handles_nested_data_exceptions_and_limits(options):
    configure_logging("api", options)
    with bind_context(request_id="test-redaction"):
        try:
            raise ValueError("访问 postgresql://user:hidden-pass@host/db Bearer hidden-token")
        except ValueError:
            get_logger("tender.test").exception(
                "失败", nested={"password": "hidden-password", "prompt": "标书全文"},
                api_key="hidden-key", message="中文\n第二行",
            )
        get_logger("tender.test").info("large", values=["原文" * 16000] * 100)
    raw = "\n".join(
        path.read_text(encoding="utf-8") for path in options.directory.rglob("*.jsonl")
    )
    for private in ("hidden-pass", "hidden-token", "hidden-password", "hidden-key", "标书全文"):
        assert private not in raw
    logs = read_logs(options.directory)
    assert logs[0]["nested"]["prompt"] == "[已隐藏]"
    assert "ValueError" in logs[0]["exception"]
    assert logs[1]["truncated"] is True
    assert logs[1]["request_id"] == "test-redaction"
    assert all(len(line.encode("utf-8")) < MAX_RECORD_BYTES for line in raw.splitlines())


def test_unwritable_files_fall_back_to_redacted_stderr(options, capsys):
    options.directory.mkdir(parents=True)
    (options.directory / "api").write_text("目录位置被文件占用", encoding="utf-8")
    configure_logging("api", options)
    get_logger("tender.test").error("cannot_write", password="do-not-leak")
    get_logger("tender.test").error("second_attempt")
    captured = capsys.readouterr().err
    assert "cannot_write" in captured
    assert "do-not-leak" not in captured
    assert captured.count("log_file_unavailable") == 1


def test_stdout_json_does_not_create_log_files(options, monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    configure_logging("beat", replace(options, output="stdout", console_format="json"))
    get_logger("tender.test").info("beat_event")
    assert json.loads(output.getvalue())["service"] == "beat"
    assert not options.directory.exists()


def test_multiple_processes_write_independent_files(options):
    code = (
        "import sys; from pathlib import Path; "
        "from tender.core.settings import LoggingSettings; "
        "from tender.core.logging import configure_logging, get_logger, shutdown_logging; "
        "configure_logging('worker', LoggingSettings(directory=Path(sys.argv[1]), output='file')); "
        "[get_logger('tender.test').info('child', index=i) for i in range(20)]; "
        "shutdown_logging()"
    )
    children = [
        subprocess.Popen(
            [sys.executable, "-X", "utf8", "-c", code, str(options.directory)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        )
        for _ in range(2)
    ]
    for child in children:
        _, stderr = child.communicate(timeout=20)
        assert child.returncode == 0, stderr
    logs = read_logs(options.directory)
    assert len(logs) == 40
    assert len({log["process_id"] for log in logs}) == 2
    assert len(list((options.directory / "worker").glob("*.jsonl"))) == 2


def test_settings_defaults_overrides_and_validation(options, monkeypatch):
    value = settings.logging_settings()
    assert value.retention_days == 30
    assert value.max_file_bytes == 104857600
    assert value.timezone == "Asia/Singapore"
    monkeypatch.setenv("LOG_RETENTION_DAYS", "7")
    assert settings.logging_settings().retention_days == 7
    for key, bad in (
        ("LOG_RETENTION_DAYS", "0"), ("LOG_RETENTION_DAYS", "-3"),
        ("LOG_MAX_FILE_BYTES", "10"), ("LOG_TIMEZONE", "wrong/zone"),
        ("LOG_OUTPUT", "db"), ("LOG_LEVEL", "EVERYTHING"),
        ("LOG_CLEANUP_INTERVAL_SECONDS", "0"),
    ):
        with monkeypatch.context() as local:
            local.setenv(key, bad)
            with pytest.raises(ValueError):
                settings.logging_settings()


@pytest.mark.parametrize("failure", ["invalid-database-url", "component-error"])
def test_api_initialization_failure_is_logged_before_process_exits(options, failure):
    # 独立解释器覆盖模块级装配；无效 DSN 或注入异常都在创建外部连接前失败。
    code = """
import sys
from pathlib import Path
from tender.core import settings
settings._ENV_FILE = Path(sys.argv[1]) / "unused.env"
if sys.argv[2] == "component-error":
    from tender.core import di
    def fail():
        raise RuntimeError("startup failed; password=startup-hidden-secret")
    di.create_api_components = fail
import tender.api.app
"""
    child = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code, str(options.directory), failure],
        env=os.environ | {
            "DATABASE_URL": "test-invalid-database-url", "LOG_OUTPUT": "file",
            "LOG_DIR": str(options.directory),
        },
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert child.returncode != 0
    expected = "ArgumentError" if failure == "invalid-database-url" else "RuntimeError"
    assert expected in child.stderr
    failures = [
        log for log in read_logs(options.directory)
        if log["event"] == "api_initialization_failed"
    ]
    assert len(failures) == 1
    entry = failures[0]
    assert entry["service"] == "api"
    assert entry["level"] == "error"
    assert expected in entry["exception"]
    assert "Traceback" in entry["exception"]
    reason = (
        "Could not parse SQLAlchemy URL" if failure == "invalid-database-url" else "startup failed"
    )
    assert reason in entry["exception"]
    assert "startup-hidden-secret" not in json.dumps(failures)


def test_asgi_requests_failures_streaming_and_concurrency(options):
    configure_logging("api", options)
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)
    failure_error = RuntimeError("password=never-expose")

    @app.get("/item/{item_id}")
    async def item(item_id: int):
        await asyncio.sleep(0)
        get_logger("tender.test").info("inside_request", item_id=item_id)
        return {"id": item_id}

    @app.get("/failed")
    async def failed():
        raise failure_error

    @app.get("/stream")
    async def stream():
        async def chunks():
            yield b"first"
            await asyncio.sleep(0)
            yield b"second"
        return StreamingResponse(chunks())

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(*(
                client.get(
                    f"/item/{index}?token=not-in-logs",
                    headers={"X-Request-ID": f"req-{index}", "Authorization": "Bearer private"},
                ) for index in range(5)
            ))
            assert all(response.headers["x-request-id"] == f"req-{index}"
                       for index, response in enumerate(responses))
            failure = await client.get("/failed", headers={"X-Request-ID": "bad id"})
            assert failure.status_code == 500
            assert len(failure.headers["x-request-id"]) == 32
            streamed = await client.get("/stream")
            assert streamed.content == b"firstsecond"
            assert len(streamed.headers["x-request-id"]) == 32
        assert get_context() == {}

    asyncio.run(check())
    logging.getLogger("uvicorn.error").error(
        "Exception in ASGI application",
        exc_info=(type(failure_error), failure_error, failure_error.__traceback__),
    )
    logs = read_logs(options.directory)
    summaries = [log for log in logs if log["event"] == "http_request_finished"]
    assert len(summaries) == 7
    inside = [log for log in logs if log["event"] == "inside_request"]
    assert all(log["request_id"] == f"req-{log['item_id']}" for log in inside)
    exceptions = [log for log in logs if "exception" in log]
    assert len(exceptions) == 1
    assert exceptions[0]["request_id"] == next(
        log["request_id"] for log in summaries if log["status_code"] == 500
    )
    assert "never-expose" not in json.dumps(logs)
    assert "not-in-logs" not in json.dumps(logs)


@pytest.mark.parametrize("interval", [None, 15])
def test_access_logs_sample_successes_but_keep_errors_and_request_context(
    options, monkeypatch, interval,
):
    from tender.api import logging as access_logging

    configure_logging("api", options)
    clock = [100.0]
    monkeypatch.setattr(access_logging, "time", SimpleNamespace(
        monotonic=lambda: clock[0], perf_counter=lambda: clock[0],
    ))
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)
    limit = throttle_access_log() if interval is None else throttle_access_log(interval)
    interval = 60 if interval is None else interval

    @app.api_route("/poll/{item_id}", methods=["GET", "POST"])
    @limit
    async def poll(item_id: int, status: int = 200):
        from fastapi.responses import JSONResponse

        await asyncio.sleep(0)
        get_logger("tender.test").info("poll_business_event")
        return JSONResponse({"id": item_id}, status_code=status)

    @app.get("/failed")
    @throttle_access_log()
    async def failed():
        raise RuntimeError("password=access-hidden-secret")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app, raise_app_exceptions=False), base_url="http://test",
        ) as client:
            responses = await asyncio.gather(*(
                client.get(f"/poll/1?tick={i}", headers={"X-Request-ID": f"poll-{i}"})
                for i in range(10)
            ))
            assert [r.headers["x-request-id"] for r in responses] == [
                f"poll-{i}" for i in range(10)
            ]
            clock[0] += interval - 1
            await client.get("/poll/1", headers={"X-Request-ID": "before-boundary"})
            clock[0] += 1
            await client.get("/poll/1", headers={"X-Request-ID": "at-boundary"})
            await client.get("/poll/2")  # 不同资源、方法及状态不能被上一种访问吞掉。
            await client.post("/poll/1")
            for status in (201, 302, 304, 400, 404, 429, 500, 503):
                for _ in range(2):
                    await client.get(f"/poll/1?status={status}")
            for _ in range(2):
                assert (await client.get("/failed")).status_code == 500
            # 错误不应刷新或清空成功分组的窗口。
            await client.get("/poll/1", headers={"X-Request-ID": "after-error"})
        assert get_context() == {}

    asyncio.run(check())
    logs = read_logs(options.directory)
    summaries = [log for log in logs if log["event"] == "http_request_finished"]
    assert len(summaries) == 19
    assert summaries[0]["suppressed_count"] == 0
    assert summaries[1]["request_id"] == "at-boundary"
    assert summaries[1]["suppressed_count"] == 10
    assert [log["status_code"] for log in summaries[7:]] == [
        400, 400, 404, 404, 429, 429, 500, 500, 503, 503, 500, 500,
    ]
    assert all(log["level"] == "warning" for log in summaries[7:13])
    assert all(log["level"] == "error" for log in summaries[13:])
    assert len([log for log in logs if log["event"] == "poll_business_event"]) == 31
    assert len([log for log in logs if "exception" in log]) == 2
    assert "access-hidden-secret" not in json.dumps(logs)
    assert "tick=" not in json.dumps(logs)


def test_access_log_decorator_preserves_sync_parameters_and_leaves_other_routes_unsampled(options):
    configure_logging("api", options)
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/poll/{item_id}")
    @throttle_access_log()
    def poll(item_id: int, request: Request, value: int = Query(ge=1)):
        get_logger("tender.test").info("sync_poll", item_id=item_id)
        return {"id": item_id, "value": value, "request_id": request.state.log_request_id}

    @app.post("/poll/{item_id}")
    def write(item_id: int):
        return {"id": item_id}

    @app.get("/manual")
    def manual():
        return {"ok": True}

    @app.get("/disabled")
    @throttle_access_log(0)
    async def disabled():
        return {"ok": True}

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test",
        ) as client:
            for index in range(3):
                response = await client.get(
                    f"/poll/7?value={index + 1}", headers={"X-Request-ID": f"sync-{index}"},
                )
                assert response.json() == {"id": 7, "value": index + 1,
                                           "request_id": f"sync-{index}"}
                assert (await client.post("/poll/7")).status_code == 200
                assert (await client.get("/manual")).status_code == 200
                assert (await client.get("/disabled")).status_code == 200
            for _ in range(2):
                assert (await client.get("/poll/7?value=0")).status_code == 422
        assert get_context() == {}

    asyncio.run(check())
    logs = read_logs(options.directory)
    summaries = [log for log in logs if log["event"] == "http_request_finished"]
    assert len(summaries) == 12
    assert len([log for log in summaries if log["route"] == "/manual"]) == 3
    assert len([log for log in summaries if log["route"] == "/disabled"]) == 3
    assert len([log for log in summaries if log["method"] == "POST"]) == 3
    assert len([log for log in summaries if log["status_code"] == 422]) == 2
    assert {log["request_id"] for log in logs if log["event"] == "sync_poll"} == {
        "sync-0", "sync-1", "sync-2",
    }


def test_access_log_decorators_use_independent_windows(options, monkeypatch):
    from tender.api import logging as access_logging

    configure_logging("api", options)
    clock = [0.0]
    monkeypatch.setattr(access_logging, "time", SimpleNamespace(
        monotonic=lambda: clock[0], perf_counter=lambda: clock[0],
    ))
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/short")
    @throttle_access_log(15)
    def short():
        return {}

    @app.get("/long")
    @throttle_access_log()
    def long():
        return {}

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test",
        ) as client:
            for seconds in (0, 14, 15, 59, 60):
                clock[0] = seconds
                await client.get("/short")
                await client.get("/long")

    asyncio.run(check())
    logs = read_logs(options.directory)
    assert len([log for log in logs if log["route"] == "/short"]) == 3
    assert len([log for log in logs if log["route"] == "/long"]) == 2


def test_only_frontend_polling_routes_enable_access_log_throttling():
    from tender.api import config, jobs, knowledge, llm, parsing, project_files, projects, versions

    selected = {
        (method, route.path)
        for module in (config, jobs, knowledge, llm, parsing, project_files, projects, versions)
        for route in module.router.routes
        if getattr(route.endpoint, "_tender_access_log_interval", 0) > 0
        for method in route.methods
    }
    # 与已确认的前端定时查询链路对应，防止扩成全局 GET 或误吞写接口的日志。
    assert selected == {("GET", "/api/v1" + path) for path in (
        "/jobs/{job_id}", "/projects/{project_id}",
        "/knowledge/collections/{collection_id}", "/knowledge/answers/{answer_id}",
        "/projects/{project_id}/analysis", "/analysis/reports/{report_id}",
        "/analysis/reports/{report_id}/modules/{module_key}/records",
        "/llm/settings", "/llm/providers", "/llm/models", "/llm/features",
    )}


def test_access_log_window_survives_many_distinct_paths_and_cleans_expired_keys(
    options, monkeypatch,
):
    from tender.api import logging as access_logging

    clock = [100.0]
    monkeypatch.setattr(access_logging, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    window = _AccessLogWindow(15)
    keys = [("GET", f"/poll/{number}", 200) for number in range(5000)]
    # 一轮含有很多不同资源时，也不能靠淘汰未过期分组重新放行重复日志。
    assert all(window.sample(key) == 0 for key in keys)
    clock[0] += 14
    assert all(window.sample(key) is None for key in keys)
    clock[0] += 1
    assert window.sample(keys[0]) == 1
    assert len(window._recent) == 1


def test_access_log_window_is_atomic_across_threads(options):
    window = _AccessLogWindow(60)
    barrier = threading.Barrier(8)

    def sample():
        barrier.wait(timeout=5)
        return window.sample(("GET", "/poll/1", 200))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: sample(), range(8)))
    assert results.count(0) == 1
    assert results.count(None) == 7


@pytest.mark.parametrize("path", ["/stream", "/api/v1/healthz"])
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
def test_interrupted_successful_stream_is_never_sampled(options, path, error_type):
    configure_logging("api", options)

    @throttle_access_log()
    async def app(scope, receive, send):
        scope["route"] = SimpleNamespace(path=path)
        scope["endpoint"] = app
        await send({"type": "http.response.start", "status": 200})
        raise error_type("stream interrupted")

    middleware = RequestLoggingMiddleware(app)

    async def noop(*args):
        pass

    async def check():
        for _ in range(3):
            scope = {"type": "http", "method": "GET", "path": path, "headers": []}
            with pytest.raises(error_type, match="stream interrupted"):
                await middleware(scope, noop, noop)
        assert get_context() == {}

    asyncio.run(check())
    logs = read_logs(options.directory)
    assert len(logs) == 3
    assert all(log["outcome"] == "interrupted" for log in logs)
    assert all(log["status_code"] == 200 and log["level"] == "error" for log in logs)


def test_celery_real_execution_and_publication_without_external_services(options, monkeypatch):
    from celery import signals

    from tender.adapters.celery_logging import CONTEXT_HEADER, install_publish_logging
    from tender.worker import logging as worker_logging
    from tender.worker.logging import install_worker_logging

    configure_logging("worker", options)
    install_worker_logging()
    install_worker_logging()
    install_publish_logging()
    app = Celery("tender", broker="memory://")
    app.conf.task_default_queue = "test_logging"
    monkeypatch.setattr(
        worker_logging, "configure_logging", lambda service: configure_logging(service, options)
    )
    signals.setup_logging.send(sender=app)

    @app.task(name="tender.test.logging")
    def job(fail=False):
        get_logger("tender.test").info("inside_task")
        if fail:
            raise RuntimeError("password=task-secret")
        return "private-result"

    try:
        with bind_context(request_id="published-request", job_id=12):
            app.send_task(job.name, args=[])
        with app.connection() as connection:
            queue = connection.SimpleQueue("test_logging")
            message = queue.get(block=False)
            headers = message.headers
            message.ack()
            queue.close()
        assert headers[CONTEXT_HEADER]["request_id"] == "published-request"
        with bind_context(request_id="outer"):
            result = job.apply(headers={CONTEXT_HEADER: {"request_id": "task-request"}})
            assert result.successful()
            assert get_context() == {"request_id": "outer"}
        assert job.apply(args=[True]).failed()
        assert get_context() == {}
    finally:
        app.close()
    logs = read_logs(options.directory)
    starts = [log for log in logs if log["event"] == "task_started"]
    assert len(starts) == 2
    assert starts[0]["request_id"] == "task-request"
    assert "request_id" not in starts[1]
    assert len([log for log in logs if log["event"] == "task_execution_failed"]) == 1
    assert "private-result" not in json.dumps(logs)
    assert "task-secret" not in json.dumps(logs)


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
@pytest.mark.parametrize("task_name", [
    "tender.worker.dispatch.dispatch_pending",
    "tender.worker.knowledge.dispatch_knowledge",
])
def test_periodic_dispatch_is_quiet_but_keeps_warnings_failures_and_retries(
    options, monkeypatch, level, task_name,
):
    from celery import Task, signals

    from tender.worker import logging as worker_logging

    worker_logging.install_worker_logging()
    monkeypatch.setattr(
        worker_logging, "configure_logging",
        lambda service: configure_logging(service, replace(options, level=level)),
    )
    # 使用相同任务名的独立探针，覆盖真实 Celery 信号，但不执行业务派发或访问数据库。
    app = Celery("tender_logging_probe", broker="memory://", set_as_current=False)
    signals.setup_logging.send(sender=app)

    class DispatchProbe(Task):
        name = task_name

        def run(self, outcome="success"):
            get_logger("tender.test").warning("dispatch_probe_warning")
            if outcome == "failure":
                raise RuntimeError("dispatch failed; password=periodic-secret")
            if outcome == "retry" and self.request.retries == 0:
                raise self.retry(countdown=0)
            return None

    probe = app.register_task(DispatchProbe())
    try:
        with bind_context(request_id="outer-request"):
            success = probe.apply()
            failure = probe.apply(args=["failure"])
            retry = probe.apply(args=["retry"])
            assert success.successful() and failure.failed() and retry.successful()
            assert get_context() == {"request_id": "outer-request"}
        assert get_context() == {}
    finally:
        app.close()
    logs = read_logs(options.directory)
    successful_lifecycle = [
        log for log in logs
        if log.get("task_id") == success.id
        and log["event"] in {"task_started", "task_finished"}
    ]
    if level == "INFO":
        assert successful_lifecycle == []
        assert not any(log["event"] == "task_started" for log in logs)
        assert not any(
            log["event"] == "task_finished" and log.get("execution_state") == "SUCCESS"
            for log in logs
        )
    else:
        assert {log["event"] for log in successful_lifecycle} == {"task_started", "task_finished"}
        assert all(log["level"] == "debug" for log in successful_lifecycle)
    assert any(
        log["event"] == "dispatch_probe_warning" and log["task_id"] == success.id
        and log["task_name"] == task_name and log["level"] == "warning"
        for log in logs
    )
    assert any(
        log["event"] == "task_execution_failed" and log["task_id"] == failure.id
        and log["level"] == "error" and "dispatch failed" in log["exception"]
        for log in logs
    )
    assert any(
        log["event"] == "task_finished" and log["task_id"] == failure.id
        and log["execution_state"] == "FAILURE" and log["level"] == "info"
        for log in logs
    )
    assert any(
        log["event"] == "task_retry" and log["task_id"] == retry.id and log["level"] == "warning"
        for log in logs
    )
    assert "periodic-secret" not in json.dumps(logs)


@pytest.mark.parametrize("traceback_kind", ["text", "object", "none"])
def test_celery_failure_preserves_exception_and_context(options, traceback_kind):
    from billiard.einfo import ExceptionInfo
    from billiard.exceptions import WorkerLostError
    from celery import Task, signals

    from tender.worker.logging import install_worker_logging

    configure_logging("worker", options)
    install_worker_logging()
    try:
        raise WorkerLostError("child worker exited; password=celery-hidden-secret")
    except WorkerLostError as error:
        failure = error
        info = ExceptionInfo()
    # 父进程信号没有活动异常；放在 except 内会让 structlog 错用 sys.exc_info 而假通过。
    traceback = {"text": info.traceback, "object": failure.__traceback__, "none": None}[
        traceback_kind
    ]
    sender = Task()
    sender.name = "tender.test.lost_worker"
    with bind_context(request_id="parent-request"):
        responses = signals.task_failure.send(
            sender=sender, task_id="lost-task", exception=failure, traceback=traceback,
            einfo=info,
        )
        assert all(result is None for _, result in responses)
        assert get_context() == {"request_id": "parent-request"}
    assert get_context() == {}
    failures = [
        log for log in read_logs(options.directory) if log["event"] == "task_execution_failed"
    ]
    assert len(failures) == 1
    entry = failures[0]
    assert entry["task_id"] == "lost-task"
    assert entry["task_name"] == sender.name
    assert entry["request_id"] == "parent-request"
    assert "WorkerLostError" in entry["exception"]
    assert "child worker exited" in entry["exception"]
    if traceback_kind != "none":
        assert "test_celery_failure_preserves_exception_and_context" in entry["exception"]
    if traceback_kind == "text":
        assert entry["exception_type"] == "WorkerLostError"
        assert "child worker exited" in entry["reason"]
    assert "celery-hidden-secret" not in json.dumps(failures)


def test_celery_nested_eager_and_thread_pool_restore_their_own_context(options):
    from tender.worker.logging import install_worker_logging

    configure_logging("worker", options)
    install_worker_logging()
    app = Celery("tender", broker="memory://")

    @app.task(name="tender.test.inner")
    def inner():
        return get_context()

    @app.task(name="tender.test.outer")
    def outer():
        before = get_context()
        child = inner.apply().get()
        assert child["task_id"] != before["task_id"]
        assert get_context() == before
        return before["task_id"]

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: outer.apply(), range(4)))
        assert all(result.successful() for result in results)
        assert len({result.result for result in results}) == 4
        assert get_context() == {}
    finally:
        app.close()
    logs = read_logs(options.directory)
    assert len([log for log in logs if log["event"] == "task_started"]) == 8
    assert len([log for log in logs if log["event"] == "task_finished"]) == 8
