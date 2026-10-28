"""慢数据库操作必须在线程中执行，不能拖住同一进程内的异步请求。"""

import asyncio
from threading import get_ident
from unittest.mock import AsyncMock, Mock

from tender.application.knowledge import service as knowledge_service
from tender.application.knowledge.service import KnowledgeService
from tender.application.llm.routing import ModelCandidate, RoutingModel
from tender.domain.shared.errors import ModelUnavailable
from tender.ports.llm.chat import Completion


def test_search_precheck_and_embedding_probe_leave_event_loop(monkeypatch):
    async def run():
        loop_thread = get_ident()

        def check_thread(*args):
            assert get_ident() != loop_thread
            return {"model_id": "fixture"}

        store = Mock()
        store.collection.side_effect = check_thread
        store.embedding_config.side_effect = check_thread
        store.sources.return_value = []
        client = AsyncMock()
        client.embed.return_value = [[1.0]]
        service = KnowledgeService(store, 1, Mock(), lambda _: client, Mock())
        monkeypatch.setattr(knowledge_service, "retrieve_chunks", AsyncMock(return_value=([], {})))
        assert (await service.search_collection(1, "查询"))["items"] == []
        assert (await service.test_embedding())["dimension"] == 1

    asyncio.run(run())


def test_routing_database_hooks_leave_event_loop_and_preserve_order():
    async def run():
        loop_thread = get_ident()
        events = []

        def check_thread(event):
            assert get_ident() != loop_thread
            events.append(event)

        def recheck(candidate):
            check_thread("recheck")
            return candidate

        def remaining(candidate):
            check_thread("cooldown")
            return 0

        def reserve(record):
            check_thread("reserve")

        def record_call(record):
            check_thread(record.status)

        def defer(candidate, delay):
            check_thread("defer")

        candidate = ModelCandidate(
            registry_model_id=1, provider_id=1, display_name="fixture", model="fixture",
            base_url="http://fixture.invalid", api_key=None, timeout=2,
            temperature=None, max_tokens=None, extra_retries=0,
        )
        client = AsyncMock()
        client.complete.side_effect = [
            ModelUnavailable("限流", http_status=429), Completion("{}", "fixture"),
        ]
        router = RoutingModel(
            "analysis", "analysis", [candidate], lambda *args, **kwargs: client, record_call,
            recheck=recheck, reserve=reserve, cooldown_remaining=remaining, defer_provider=defer,
            rate_limit_backoff_seconds=0.001,
        )
        try:
            assert (await router.complete("查询")).model == "fixture"
        finally:
            await router.aclose()
        assert events.index("reserve") < events.index("error") < events.index("defer")
        assert events[-1] == "ok"

    asyncio.run(run())
