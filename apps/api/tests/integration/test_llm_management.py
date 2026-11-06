"""在独立事务 schema 内运行真实迁移与管理接口，结束回滚，不触碰业务记录。"""

import asyncio
import importlib.util
import os
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from tender.api.llm import routes as llm
from tender.api.shared.errors import ApiProblem
from tender.core.settings import database_url
from tender.domain.shared.errors import ModelInUse
from tender.ports.llm.chat import Completion

pytestmark = pytest.mark.skipif(os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库")


class Probe:
    async def complete(self, _):
        return Completion(
            content='{"ok":true}', model="fixture", prompt_tokens=2, completion_tokens=3
        )

    async def aclose(self):
        pass


@pytest.fixture
def env():
    db = create_engine(database_url(), connect_args={"connect_timeout": 5})
    with db.connect() as c, c.begin() as transaction:
        schema = "llm_test_" + uuid4().hex
        c.execute(text(f"CREATE SCHEMA {schema}"))
        c.execute(text(f"SET LOCAL search_path TO {schema}, public"))
        # 全链迁移能发现多列 ALTER、部分唯一索引与新增测试表之间的真实兼容问题。
        root = Path(__file__).resolve().parents[2] / "alembic" / "versions"
        for path in sorted(root.glob("*.py")):
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for statement in module._STATEMENTS:
                # 0008 有显式 schema，测试必须重命名它，不能触碰业务 checkpoint 空间。
                statement = statement.replace("SCHEMA agent_runtime", f"SCHEMA {schema}_agents")
                c.execute(text(statement))
        facade = SimpleNamespace(connect=lambda: nullcontext(c), begin=lambda: nullcontext(c))
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    components=SimpleNamespace(
                        engine=facade, model_gateway=lambda *a, **kw: Probe()
                    )
                )
            )
        )
        yield request, c
        transaction.rollback()
    db.dispose()


def provider(request, **kwargs):
    return llm.create_provider(
        llm.ProviderCreate(
            name="测试供应商", base_url="http://localhost/v1", auth_mode="none", **kwargs
        ),
        request,
    )


def model(request, pid, **kwargs):
    return llm.create_model(llm.ModelCreate(provider_id=pid, model_id="fixture", **kwargs), request)


def test_model_crud_binding_revision_and_history(env):
    request, _ = env
    p = provider(request)
    m = model(request, p["id"])
    assert m["enabled"] is True
    result = asyncio.run(llm.test_model(m["id"], request))
    assert result["status"] == "ok"
    assert llm.get_test(result["test_id"], request)["status"] == "ok"
    feature = llm.replace_bindings(
        "analysis",
        llm.BindingsRequest(
            model_ids=[m["id"]], revision=1, failover_limit=2, max_total_requests=4
        ),
        request,
    )
    assert feature["revision"] == 2
    with pytest.raises(ApiProblem) as conflict:
        llm.replace_bindings("analysis", llm.BindingsRequest(model_ids=[], revision=1), request)
    assert conflict.value.status_code == 412
    assert llm._feature_item(request, "analysis")["bindings"][0]["model_row_id"] == m["id"]
    with pytest.raises(ModelInUse):
        llm.delete_model(m["id"], request)
    llm.update_model(
        m["id"], llm.ModelPatch(display_name="新名称", revision=m["revision"]), request
    )
    with pytest.raises(ApiProblem) as conflict:
        llm.update_model(
            m["id"], llm.ModelPatch(display_name="覆盖", revision=m["revision"]), request
        )
    assert conflict.value.status_code == 412
    current = llm.list_models(request)["items"][0]
    assert current["test_validity"] == "valid"
    calls = llm.list_calls(request, limit=25, offset=0)
    assert calls["items"][0]["display_name"] == "fixture"
    llm.replace_bindings("analysis", llm.BindingsRequest(model_ids=[], revision=2), request)
    llm.delete_provider(p["id"], request)
    assert llm.list_models(request)["items"] == []
    assert llm.list_calls(request, limit=25, offset=0)["total"] == 1


def test_decimal_temperature_survives_test_and_form_save(env):
    # NUMERIC 温度经 psycopg 是 Decimal：测试、改名和原值回存都不能被误判。
    request, _ = env
    p = provider(request)
    m = model(request, p["id"], temperature=0.2)
    # 修复前 _validate 收到 Decimal 就直接 422，测试与改名都会失败。
    assert asyncio.run(llm.test_model(m["id"], request))["status"] == "ok"
    renamed = llm.update_model(
        m["id"], llm.ModelPatch(display_name="改名", revision=m["revision"]), request
    )
    assert renamed["temperature"] == 0.2
    assert renamed["test_validity"] == "valid"
    # 表单回存相同温度（float 0.2 对库里 Decimal 0.20）不能被当作配置变化。
    saved = llm.update_model(
        m["id"], llm.ModelPatch(temperature=0.2, revision=renamed["revision"]), request
    )
    assert saved["temperature"] == 0.2
    assert saved["test_validity"] == "valid"


def test_provider_noop_keeps_test_valid_but_address_change_invalidates(env):
    request, _ = env
    p = provider(request)
    m = model(request, p["id"])
    asyncio.run(llm.test_model(m["id"], request))
    p = llm.update_provider(
        p["id"],
        llm.ProviderPatch(
            name="改名", base_url=p["base_url"], auth_mode="none", revision=p["revision"]
        ),
        request,
    )
    assert llm.list_models(request)["items"][0]["test_validity"] == "valid"
    llm.update_provider(p["id"], llm.ProviderPatch(base_url="http://localhost/other"), request)
    assert llm.list_models(request)["items"][0]["test_validity"] == "config_changed"


def test_latest_started_test_wins_and_old_provider_revision_cannot_write_back(env):
    request, c = env
    p = provider(request)
    m = model(request, p["id"])
    db = request.app.state.components.engine
    row = llm._model_row(db, m["id"])
    older = llm._begin_test(db, row, "language", True)
    newer = llm._begin_test(db, row, "language", True)
    assert llm.list_models(request)["items"][0]["test_validity"] == "running"
    llm._finish_test(db, row, older, "ok", None, 1, True)
    assert llm.list_models(request)["items"][0]["last_test_status"] == "running"
    llm._finish_test(db, row, newer, "error", "模拟失败", 2, True)
    assert llm.list_models(request)["items"][0]["last_test_status"] == "error"
    latest = llm._begin_test(db, row, "language", True)
    llm.update_provider(p["id"], llm.ProviderPatch(base_url="http://localhost/new"), request)
    llm._finish_test(db, row, latest, "ok", None, 1, True)
    assert llm.list_models(request)["items"][0]["test_validity"] == "config_changed"
    assert (
        c.execute(text("SELECT status FROM llm_test WHERE id=:id"), {"id": latest}).scalar() == "ok"
    )


def test_import_is_enabled_deduplicated_and_requires_matching_kind(env):
    request, _ = env
    p = provider(request)
    payload = llm.ImportRequest(
        model_ids=["a", "b", "a"],
        kind="embedding",
        api_mode="embeddings",
        capabilities=["text_input", "embedding"],
    )
    assert llm.import_models(p["id"], payload, request)["created"] == 2
    models = llm.list_models(request)["items"]
    assert all(m["enabled"] for m in models)
    llm.update_model(
        models[0]["id"], llm.ModelPatch(enabled=False, revision=models[0]["revision"]), request
    )
    assert llm.import_models(p["id"], payload, request)["skipped"] == 2
    # 重复导入只跳过已有模型，不能覆盖用户手动停用的状态。
    assert llm.list_models(request)["items"][0]["enabled"] is False
    with pytest.raises(ApiProblem):
        llm.replace_bindings(
            "analysis", llm.BindingsRequest(model_ids=[models[0]["id"]], revision=1), request
        )
    assert llm._feature_item(request, "analysis")["bindings"] == []


def test_rerank_catalog_is_explicitly_unsupported_without_network(env):
    request, _ = env
    p = provider(request, protocol="rerank_http")
    result = asyncio.run(llm.test_provider(p["id"], request))
    assert result["status"] == "unsupported"
    assert llm.list_providers(request)["items"][0]["test_validity"] == "unsupported"


def test_call_chain_filters_and_orders_requests(env):
    request, c = env
    invocation = uuid4()
    for ordinal in (3, 1, 2):
        c.execute(
            text("""INSERT INTO llm_call_log(
                purpose,status,latency_ms,invocation_id,request_ordinal)
            VALUES ('extract','error',1,:id,:ordinal)"""),
            {"id": invocation, "ordinal": ordinal},
        )
    result = llm.list_calls(request, invocation_id=invocation, limit=25, offset=0)
    assert [r["request_ordinal"] for r in result["items"]] == [1, 2, 3]
    assert all(r["prompt_tokens"] is None for r in result["items"])


def test_test_expiry_is_evaluated_when_read(env):
    request, c = env
    p = provider(request)
    m = model(request, p["id"])
    asyncio.run(llm.test_model(m["id"], request))
    c.execute(
        # 过期依据分能力测试的完成时刻，不能只修改旧的模型摘要字段。
        text("UPDATE llm_test SET finished_at=:at"),
        {"at": datetime.now(UTC) - timedelta(days=7)},
    )
    assert llm.list_models(request)["items"][0]["test_validity"] == "expired"


def test_test_history_accepts_empty_and_model_filters(env):
    request, _ = env
    assert llm.list_tests(request, limit=10)["items"] == []
    p = provider(request)
    m = model(request, p["id"])
    result = asyncio.run(llm.test_model(m["id"], request))
    assert llm.list_tests(request, limit=10)["items"][0]["id"] == result["test_id"]
    assert len(llm.list_tests(request, model_id=m["id"], limit=10)["items"]) == 1
    assert llm.list_tests(request, model_id=m["id"] + 1, limit=10)["items"] == []


def test_embedding_probe_returns_measured_vector_shape(env, monkeypatch):
    request, _ = env
    p = provider(request)
    m = model(
        request,
        p["id"],
        kind="embedding",
        api_mode="embeddings",
        capabilities=["text_input", "embedding"],
    )

    class EmbeddingProbe:
        async def embed(self, texts):
            assert texts == ["知识库连接测试"]
            return [[0.6, 0.8]]

        async def aclose(self):
            pass

    monkeypatch.setattr(llm, "create_embedding_gateway", lambda _: EmbeddingProbe())
    result = asyncio.run(llm.test_model(m["id"], request))
    assert (result["status"], result["vector_count"], result["embedding_dimensions"]) == (
        "ok",
        1,
        2,
    )
    assert llm.list_calls(request, limit=10, offset=0)["items"][0]["vector_count"] == 1


def test_complete_configuration_roundtrip_and_capability_proofs_are_independent(env, monkeypatch):
    from tender.application.llm.probes import PROBE_IMAGE

    request, _ = env
    p = provider(request, protocol="gemini")
    m = model(
        request,
        p["id"],
        kind="embedding",
        api_mode="embeddings",
        capabilities=["text_input", "embedding", "image_input"],
        parameters={"dimensions": 3},
        supported_parameters=["dimensions"],
    )
    assert m["embedding_input_type"] == "multimodal"
    assert m["parameters"] == {"dimensions": 3}
    assert m["supported_parameters"] == ["dimensions"]
    assert m["embedding_space_id"]

    class Embedding:
        async def embed(self, texts):
            return [[0.1, 0.2, 0.3]]

        async def embed_inputs(self, inputs):
            assert inputs[0].images == (PROBE_IMAGE,)
            return [[0.1, 0.2, 0.3]]

        async def aclose(self):
            pass

    monkeypatch.setattr(llm, "create_embedding_gateway", lambda config: Embedding())
    asyncio.run(llm.test_model(m["id"], request, llm.TestRequest(capability="embedding")))
    fresh = llm.list_models(request)["items"][0]
    assert fresh["capability_tests"]["embedding"]["validity"] == "valid"
    assert "multimodal_embedding" not in fresh["capability_tests"]
    asyncio.run(
        llm.test_model(m["id"], request, llm.TestRequest(capability="multimodal_embedding"))
    )
    fresh = llm.list_models(request)["items"][0]
    assert fresh["capability_tests"]["multimodal_embedding"]["validity"] == "valid"
    changed = llm.update_model(
        m["id"], llm.ModelPatch(parameters={"dimensions": 4}, revision=m["revision"]), request
    )
    assert changed["embedding_space_id"] != m["embedding_space_id"]
    assert all(t["validity"] == "config_changed" for t in changed["capability_tests"].values())


def test_image_model_binding_preview_history_and_cleanup(env, monkeypatch):
    from tender.application.llm.probes import PROBE_IMAGE

    request, c = env
    p = provider(request)
    m = model(
        request,
        p["id"],
        kind="image_generation",
        api_mode="image_generation",
        capabilities=["text_input", "image_generation"],
        parameters={"quality": "low"},
    )

    class Image:
        async def generate(self, prompt):
            return PROBE_IMAGE

        async def aclose(self):
            pass

    monkeypatch.setattr(llm, "create_image_gateway", lambda config: Image())
    result = asyncio.run(llm.test_model(m["id"], request))
    assert result["image_count"] == 1
    test = llm.get_test(result["test_id"], request)
    assert "preview_data" not in test and test["result"]["preview_url"]
    assert llm.test_preview(result["test_id"], request).body == PROBE_IMAGE.data
    assert llm.list_calls(request, limit=25, offset=0)["items"][0]["image_count"] == 1
    # 模型显式测试可用，不应把尚无业务消费者的绑定伪装成有效设置。
    with pytest.raises(ApiProblem) as unavailable:
        llm.replace_bindings(
            "image_generation", llm.BindingsRequest(model_ids=[m["id"]], revision=1), request
        )
    assert unavailable.value.code == "feature_unavailable"
    inactive = next(
        f for f in llm.list_features(request)["items"] if f["key"] == "image_generation"
    )
    assert inactive["binding_available"] is False
    assert llm.replace_bindings(
        "image_generation", llm.BindingsRequest(model_ids=[], revision=1), request
    )["bindings"] == []
    llm.update_model(
        m["id"], llm.ModelPatch(parameters={"quality": "medium"}, revision=m["revision"]), request
    )
    with pytest.raises(ApiProblem) as expired:
        llm.test_preview(result["test_id"], request)
    assert expired.value.status_code == 410
    c.execute(
        text("UPDATE llm_test SET invalidated_at=now()-interval '25 hours' WHERE id=:id"),
        {"id": result["test_id"]},
    )
    llm.list_tests(request, limit=30)
    assert (
        c.execute(
            text("SELECT preview_data FROM llm_test WHERE id=:id"), {"id": result["test_id"]}
        ).scalar()
        is None
    )


def test_unconfigured_test_capability_is_rejected_before_a_request(env):
    request, c = env
    p = provider(request)
    m = model(request, p["id"])
    with pytest.raises(ApiProblem) as unsupported:
        asyncio.run(llm.test_model(m["id"], request, llm.TestRequest(capability="vision")))
    assert unsupported.value.status_code == 422
    assert c.execute(text("SELECT count(*) FROM llm_test")).scalar() == 0


def test_running_test_is_registered_before_send_and_recovers_as_unknown(env, monkeypatch):
    from fastapi import BackgroundTasks

    request, c = env
    p = provider(request)
    m = model(request, p["id"])
    tasks = BackgroundTasks()
    accepted = asyncio.run(
        llm.start_model_test(m["id"], request, tasks, llm.TestRequest(capability="text"))
    )
    test = llm.get_test(accepted["test_id"], request)
    assert test["status"] == "running"
    assert llm.list_calls(request, limit=25, offset=0)["items"][0]["status"] == "running"
    # 模拟 API 在受理后崩溃：超出原请求超时与宽限后只收敛状态，不执行待处理回调。
    c.execute(
        text("UPDATE llm_test SET created_at=now()-interval '3 minutes' WHERE id=:id"),
        {"id": test["id"]},
    )
    recovered = llm.get_test(test["id"], request)
    assert recovered["status"] == recovered["validity"] == "unknown"
    assert llm.list_calls(request, limit=25, offset=0)["items"][0]["status"] == "unknown"


def test_json_consumers_reject_language_model_without_json_and_capability_removal(env):
    request, _ = env
    p = provider(request)
    m = model(request, p["id"], capabilities=["text_input"])
    with pytest.raises(ApiProblem):
        llm.replace_bindings(
            "analysis", llm.BindingsRequest(model_ids=[m["id"]], revision=1), request
        )
    m = llm.update_model(
        m["id"],
        llm.ModelPatch(capabilities=["text_input", "json_output"], revision=m["revision"]),
        request,
    )
    llm.replace_bindings("analysis", llm.BindingsRequest(model_ids=[m["id"]], revision=1), request)
    with pytest.raises(ApiProblem) as invalid:
        llm.update_model(
            m["id"], llm.ModelPatch(capabilities=["text_input"], revision=m["revision"]), request
        )
    assert invalid.value.status_code == 409


def test_form_expanding_default_parameters_does_not_invalidate_proof(env):
    request, _ = env
    p = provider(request)
    m = model(request, p["id"])
    asyncio.run(llm.test_model(m["id"], request))
    fresh = llm.update_model(
        m["id"],
        llm.ModelPatch(
            display_name="只改展示名",
            supported_parameters=m["supported_parameters"],
            parameters={},
            capabilities=list(reversed(m["capabilities"])),
            revision=m["revision"],
        ),
        request,
    )
    assert fresh["test_validity"] == "valid"
