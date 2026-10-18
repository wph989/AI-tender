"""统一传播已有的日志关联字段，覆盖 send_task 和 apply_async 等发布入口。"""

from __future__ import annotations

from celery.signals import before_task_publish

from tender.core.logging import get_context

CONTEXT_HEADER = "tender_log_context"


def _publish_context(sender=None, headers=None, **kwargs) -> None:
    if not isinstance(sender, str) or not sender.startswith("tender.") or headers is None:
        return
    # 子任务使用自己的 task_id；不把父任务 ID 误标为子任务 ID。
    context = {key: value for key, value in get_context().items() if key != "task_id"}
    if context:
        headers[CONTEXT_HEADER] = context


def install_publish_logging() -> None:
    before_task_publish.connect(
        _publish_context, weak=False, dispatch_uid="tender.log.publish"
    )
