"""派发闩锁：阶段推进时必须把 dispatched_at 交还给闸门（防回归）。

`dispatched_at` 的语义是「**本阶段**已经投递过了」，不是「这条 job 投递过」。
派发闸门的候选条件是 `dispatched_at IS NULL`
（见 adapters/pg/repositories/jobs/dispatch.py 的 pending_jobs），
所以任何把 job 从受闸门的阶段推进到**下一个**阶段的 UPDATE，都必须同时清掉这个闩锁。

漏掉的后果不是报错，而是静默停住：job 停在 pending，beat 每 5 秒扫一遍都找不到它，
界面上表现为「解析永远在排队」。2026-10-01 联调时正是踩到这里——
转换完成把 stage 从 converting 改成 submitting，却没有清 dispatched_at。

为什么用源码断言而不是行为断言：这段逻辑要跑起来得有 PostgreSQL、MinIO 和一次真实的
Office 转换，属于端到端范畴；而这条不变式是**写法**层面的，源码断言能在改动当刻变红，
比等到联调发现便宜得多。它钉不住语义，只钉住「这一行还在」。
"""

from __future__ import annotations

import inspect

from tender.adapters.pg.repositories.documents.pipeline import DocumentPipelineRepository


def test_parse_handoff_clears_dispatch_latch() -> None:
    """转换完成、交接给解析的那条 UPDATE 必须清空 dispatched_at。"""
    source = inspect.getsource(DocumentPipelineRepository.finish_file_version)
    assert "status=status" in source and "stage=stage" in source, (
        "阶段推进的写法变了，请同步检查本测试的前提"
    )
    assert "dispatched_at=case(" in source and "null()" in source, (
        "推进到 submitting 时没有清 dispatched_at：派发闸门会永远看不到这条 job，解析将停在 pending"
    )


def test_latch_is_preserved_when_the_job_stops_here() -> None:
    """不进入解析（should_parse=False）时不能清闩锁。

    这条 job 会直接以 completed 收尾；把闩锁清掉会让结算口径里的「已派发」对不上，
    也会让后续如果有人重开这一行时误判成「从未派发」。

    ORM 写法下这条不变式落在 `case` 的 `else_` 分支：只有 should_parse 为真才写 NULL，
    否则必须原样保留 `Job.dispatched_at`。
    """
    source = inspect.getsource(DocumentPipelineRepository.finish_file_version)
    assert "else_=Job.dispatched_at" in source, "闩锁只应在进入下一阶段时清空，不能无条件清"
