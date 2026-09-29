"""派发计划：在途上限与 stage→任务映射（设计文档 10 第 3.5 节）。"""

from __future__ import annotations

from tender.worker.dispatch import STREAMS, _stage_list, capacity


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


def test_streams_cover_the_three_gated_queues_and_export() -> None:
    """三条队列各自受名下的 max_inflight 约束；导出只借道派发，不设闸门。"""
    limits = {stream.name: stream.limit_key for stream in STREAMS}
    assert limits == {
        "convert": "convert.max_inflight",
        "parse": "parse.max_inflight",
        "extract": "extract.max_inflight",
        "export": None,
    }


def test_parse_stream_covers_post_conversion_handoff() -> None:
    """转换完成后的交接用的也是 submitting：漏掉它解析就永远停在 pending。"""
    parse = next(stream for stream in STREAMS if stream.name == "parse")
    assert parse.stages == ("submitting",)
    assert parse.task_name == "tender.worker.tasks.submit_parse"


def test_stage_list_renders_quoted_constants() -> None:
    """stage 是拼进 SQL 的常量：写错引号会变成语法错误，必须在单测里钉住形态。"""
    convert = next(stream for stream in STREAMS if stream.name == "convert")
    assert _stage_list(convert) == "'converting', 'probing'"
