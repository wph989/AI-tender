"""模型测试的进程活性与生成超时分离；长响应、取消和失联各自结算。"""

import asyncio
from contextlib import nullcontext

import pytest

from tender.application.llm.service import LlmService
from tender.ports.llm.chat import Completion


class Repository:
    def __init__(self):
        self.heartbeats = 0
        self.status = "running"
        self.saved = []

    def transaction(self):
        return nullcontext(self)

    def heartbeat_test(self, test_id):
        self.heartbeats += 1
        return self.status == "running"

    def lock_test(self, test_id):
        return {"status": self.status, "error_message": "原测试失联"}

    def store_test_result(self, test_id, **values):
        self.saved.append(values["result"])

    def record_call(self, **values):
        pass

    def finish_test(self, row, test_id, **values):
        self.status = values["status"]


def service(repository, probe):
    return LlmService(repository, lambda *a, **kw: probe, embedding_gateway=lambda _: probe,
                      image_gateway=lambda _: probe, rerank_gateway=lambda _: probe)


ROW = {"kind": "language", "base_url": "http://test", "model_id": "fixture",
       "id": 1, "provider_id": 1, "auth_mode": "none", "timeout_seconds": 0.01,
       "total_timeout_seconds": None, "temperature": None, "max_tokens": None,
       "protocol": "openai_compatible", "api_mode": "chat_completions",
       "parameters": {}, "capabilities": ["text_input", "json_output"]}


def test_long_text_test_renews_and_is_not_cut_off_by_old_interval(monkeypatch):
    async def run():
        original_sleep = asyncio.sleep
        async def sleep(seconds):
            await original_sleep(0.01 if seconds == 15 else seconds)
        monkeypatch.setattr(asyncio, "sleep", sleep)
        class Probe:
            async def complete(self, prompt):
                # 端口返回前模拟持续收流；服务不能再用间隔值包住整个请求。
                await original_sleep(0.06)
                return Completion('{"ok":true}', "fixture")
            async def aclose(self):
                pass
        repository = Repository()
        result = await service(repository, Probe()).run_model_test(ROW, 1, "text")
        assert result["status"] == repository.status == "ok"
        assert repository.heartbeats >= 1
        count = repository.heartbeats
        await original_sleep(0.03)
        assert repository.heartbeats == count
    asyncio.run(run())


def test_cancellation_stores_unknown_and_stops_renewal():
    async def run():
        entered = asyncio.Event()
        class Probe:
            async def complete(self, prompt):
                entered.set()
                await asyncio.Future()
            async def aclose(self):
                pass
        repository = Repository()
        task = asyncio.create_task(service(repository, Probe()).run_model_test(ROW, 1, "text"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert repository.status == "unknown"
        assert len(repository.saved) == 1
    asyncio.run(run())
