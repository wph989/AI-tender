"""测试进程中断只能判为未知，不自动重发；临时图片与测试事实分别保留。"""

from __future__ import annotations

from sqlalchemy import Engine, func, literal, update
from sqlalchemy.dialects.postgresql import INTERVAL

from tender.adapters.pg.models import LlmCallLog, LlmTest


def maintain_model_tests(db: Engine) -> None:
    with db.begin() as c:
        # 超时口径按「配置的等待预算 + 30 秒容差」计算，避免把仍在等的测试误判为未知。
        # make_interval 只按位置传参：秒数是第 7 个，SQLAlchemy 的 func 不支持 `secs=>`。
        stale = LlmTest.created_at + func.make_interval(
            0, 0, 0, 0, 0, 0, LlmTest.timeout_seconds + 30
        ) < func.now()
        c.execute(
            update(LlmTest)
            .where(LlmTest.status == "running", stale)
            .values(
                status="unknown",
                finished_at=func.now(),
                error_message="测试执行中断或超时，供应商结果未知；请核实后再测试",
            )
        )
        c.execute(
            update(LlmCallLog)
            .where(
                LlmTest.call_log_id == LlmCallLog.id,
                LlmTest.status == "unknown",
                LlmCallLog.status == "running",
            )
            .values(status="unknown", error_message=LlmTest.error_message)
        )
        # LEAST/NULL 语义：invalidated_at 为空时以 finished_at 为准（Postgres 的 LEAST 忽略 NULL）。
        c.execute(
            update(LlmTest)
            .where(
                LlmTest.preview_data.is_not(None),
                func.least(
                    LlmTest.invalidated_at,
                    LlmTest.finished_at + literal("7 days", type_=INTERVAL),
                )
                <= func.now() - literal("24 hours", type_=INTERVAL),
            )
            .values(preview_data=None, preview_mime=None)
        )
