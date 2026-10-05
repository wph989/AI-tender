"""测试进程中断只能判为未知，不自动重发；临时图片与测试事实分别保留。"""

from sqlalchemy import Engine, text


def maintain_model_tests(db: Engine) -> None:
    with db.begin() as c:
        c.execute(
            text("""UPDATE llm_test SET status='unknown',finished_at=now(),
            error_message='测试执行中断或超时，供应商结果未知；请核实后再测试'
            WHERE status='running'
            AND created_at + (timeout_seconds + 30) * interval '1 second' < now()""")
        )
        c.execute(
            text("""UPDATE llm_call_log l SET status='unknown',error_message=t.error_message
            FROM llm_test t WHERE t.call_log_id=l.id
            AND t.status='unknown' AND l.status='running'""")
        )
        c.execute(
            text("""UPDATE llm_test SET preview_data=NULL,preview_mime=NULL
            WHERE preview_data IS NOT NULL AND LEAST(invalidated_at,finished_at + interval '7 days')
                <= now() - interval '24 hours'""")
        )
