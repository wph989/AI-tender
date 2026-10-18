"""派发计划：在途上限与 stage→任务映射（设计文档 10 第 3.5 节）。"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from tender.adapters.pg.repositories.jobs.dispatch import pending_jobs
from tender.worker.dispatch import STREAMS, capacity


def test_capacity_subtracts_inflight() -> None:
    assert capacity(4, 1) == 3


def test_capacity_never_goes_negative() -> None:
    """配置下调时不取消已在途请求，只是停止新派发（10 第 3.5 节第 4 条）。"""
    assert capacity(2, 5) == 0


def test_capacity_none_means_unlimited() -> None:
    assert capacity(None, 99) is None


def test_every_stream_has_a_task_and_stages() -> None:
    for stream in STREAMS:
        assert stream.stages, stream.name
        assert stream.task_name.startswith("tender.worker."), stream.name
        if stream.limit_key is not None:
            assert stream.limit_key.endswith(".max_inflight"), stream.limit_key


def test_streams_only_dispatch_conversion_and_parsing() -> None:
    """文件派发只保留转换和解析，专题分析由报告调度器执行。"""
    limits = {stream.name: stream.limit_key for stream in STREAMS}
    assert limits == {
        "convert": "convert.max_inflight",
        "parse": "parse.max_inflight",
    }


def test_parse_stream_covers_post_conversion_handoff() -> None:
    """转换完成后的交接用的也是 submitting：漏掉它解析就永远停在 pending。"""
    parse = next(stream for stream in STREAMS if stream.name == "parse")
    assert parse.stages == ("submitting",)
    assert parse.task_name == "tender.worker.tasks.submit_parse"


def test_pending_jobs_scope_to_stream_stages() -> None:
    """stage 由绑定参数带入：写错值不再是语法错误，改在编译结果上钉住各线的筛选条件。"""
    convert = next(stream for stream in STREAMS if stream.name == "convert")
    sql = str(
        pending_jobs(convert.stages, 7, 3).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "job.stage IN ('converting', 'probing')" in sql
