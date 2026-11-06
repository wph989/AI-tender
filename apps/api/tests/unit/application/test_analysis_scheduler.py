"""调度等待与心跳：配额等待指数退避，权限复核按固定间隔节流。"""

import asyncio
import random
from datetime import UTC, datetime, timedelta

import pytest

from tender.application.analysis.execution import (
    FULL_ACCESS_HEARTBEATS,
    HEARTBEAT_INTERVAL_SECONDS,
    model_recovery_delay,
    next_claim_delay,
    wait_for_claim,
)
from tender.application.analysis.runtime import AgentRuntime

# 与 adapters/pg/repositories/analysis/runtime.py 的租约窗口保持一致。
LEASE_SECONDS = 45


def test_claim_backoff_doubles_caps_and_jitters():
    assert next_claim_delay(1, 0.0) == 0.5
    assert next_claim_delay(1, 1.0) == 1.0
    assert next_claim_delay(2, 1.0) == 2.0
    assert next_claim_delay(3, 1.0) == 4.0
    assert next_claim_delay(4, 1.0) == 8.0
    # 封顶 8 秒，抖动仍落在 0.5—1.0 倍区间。
    assert next_claim_delay(10, 1.0) == 8.0
    assert next_claim_delay(10, 0.0) == 4.0
    assert all(
        0.5 <= next_claim_delay(round_no, value) / min(2 ** (round_no - 1), 8) <= 1.0
        for round_no in range(1, 8)
        for value in (0.0, 0.5, 1.0)
    )


def test_claim_backoff_resets_after_success():
    waited = [next_claim_delay(round_no, 0.0) for round_no in range(1, 8)]
    assert waited[:4] == [0.5, 1.0, 2.0, 4.0] and waited[-1] == 4.0
    # 领取成功后调用方把轮次归零；下一次等待重新从 1 秒档开始。
    assert next_claim_delay(1, 0.0) == 0.5


@pytest.mark.parametrize("attempt", [1025, 100_000_000])
def test_long_wait_backoff_caps_before_integer_to_float_conversion(attempt):
    assert next_claim_delay(attempt, 1.0) == 8.0
    assert next_claim_delay(attempt, 0.0) == 4.0
    assert model_recovery_delay(attempt, 31.0) == 30.0
    assert model_recovery_delay(attempt, 30.0) is None


def test_model_recovery_backoff_keeps_existing_intervals():
    assert [model_recovery_delay(n, 31.0) for n in range(1, 5)] == [5.0, 15.0, 30.0, 30.0]


def test_heartbeat_interval_is_three_times_less_than_lease():
    assert HEARTBEAT_INTERVAL_SECONDS * 3 <= LEASE_SECONDS
    # 每两次心跳做一次完整权限复核，间隔仍在租约窗口内。
    assert HEARTBEAT_INTERVAL_SECONDS * FULL_ACCESS_HEARTBEATS == 30.0


class _Store:
    def __init__(self):
        self.heartbeats = 0
        self.claims = 0

    def heartbeat(self):
        self.heartbeats += 1

    def claim(self):
        self.claims += 1
        return True


class _DB:
    def __init__(self, store):
        self.store = store
        self.status_checks = 0
        self.full_checks = 0

    def accessible_report_status(self, report_id):
        self.status_checks += 1
        return "running"

    def collections_for_project(self, project_id):
        self.full_checks += 1
        return set()

    def sources(self, allowed):
        return []

    def agent_run_store(self, report, run):
        return self.store


def test_heartbeat_skips_full_access_check_between_full_intervals():
    store = _Store()
    db = _DB(store)
    runtime = AgentRuntime(db, {"id": 1, "project_id": 1}, {"id": 2}, [])
    runtime.heartbeat(True)
    assert (db.status_checks, db.full_checks, store.heartbeats) == (1, 1, 1)
    runtime.heartbeat(False)
    # 轻量心跳仍查一次报告状态以便在 15 秒内发现取消，但不做资料权限全量复核。
    assert (db.status_checks, db.full_checks, store.heartbeats) == (2, 1, 2)
    runtime.heartbeat(True)
    assert (db.status_checks, db.full_checks, store.heartbeats) == (3, 2, 3)


def test_claim_defers_access_check_to_waiting_loop():
    store = _Store()
    db = _DB(store)
    runtime = AgentRuntime(db, {"id": 1, "project_id": 1}, {"id": 2}, [])
    assert runtime.claim()
    assert store.claims == 1 and db.status_checks == 0
    runtime.check_access()
    assert db.full_checks == 1


class _WaitingRuntime:
    def __init__(self, failures):
        self.failures = failures
        self.claims = 0
        self.checks = 0
        self.events = []
        self.run = {}

    def check_access(self):
        self.checks += 1

    def claim(self):
        self.claims += 1
        if self.failures:
            self.failures -= 1
            return False
        return True

    def event(self, kind, detail=None):
        self.events.append((kind, detail))


def test_wait_for_claim_throttles_access_checks_and_records_one_wait_event(monkeypatch):
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    monkeypatch.setattr(random, "random", lambda: 1.0)
    runtime = _WaitingRuntime(failures=10)

    asyncio.run(wait_for_claim(runtime))

    assert runtime.claims == 11
    assert delays == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0]
    # 初始一次 + 累计等待每超过 30 秒一次（约 31 秒、63 秒）；不是每轮一次。
    assert runtime.checks == 3
    assert runtime.events == [("claim_wait", {"seconds": 31, "rounds": 6})]


def test_wait_for_claim_stops_when_module_deadline_passed():
    runtime = _WaitingRuntime(failures=1)
    runtime.run = {"deadline_at": datetime.now(UTC) - timedelta(seconds=1)}
    with pytest.raises(TimeoutError, match="总时长预算"):
        asyncio.run(wait_for_claim(runtime))
    assert runtime.claims == 0
    assert runtime.checks == 1


def test_wait_for_claim_can_acquire_after_over_a_thousand_waits(monkeypatch):
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    monkeypatch.setattr(random, "random", lambda: 1.0)
    runtime = _WaitingRuntime(failures=1100)
    asyncio.run(wait_for_claim(runtime))
    assert runtime.claims == 1101
    assert len(delays) == 1100 and max(delays) == 8.0
    assert len(runtime.events) == 1
    assert 1 < runtime.checks < 300
