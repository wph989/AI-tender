"""部署消费队列必须覆盖生产者路由，避免迁移队列后 Agent 永久排队。"""

import re
from pathlib import Path

import pytest

from tender.adapters.jobs.celery_queue import create_celery_app

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("scripts/start-backend.ps1", r"'-Q',\s*'([^']+)'"),
        ("docker-compose.yml", r"- -Q[ \t]*\n\s*- ([a-z,]+)"),
        ("本地启动指南.md", r"-Q ([a-z,]+)"),
    ],
)
def test_deployment_consumes_all_routed_queues(path, pattern):
    # 读取独立部署入口而非复制路由常量，才会发现生产者与消费者之间的漏接。
    content = (ROOT / path).read_text(encoding="utf-8-sig")
    configured = re.findall(pattern, content)
    assert configured, f"未识别 {path} 的 worker 队列，检查部署格式是否变化"
    app = create_celery_app()
    try:
        required = {app.conf.task_default_queue} | {
            route["queue"] for route in app.conf.task_routes.values()
        }
        for queues in configured:
            assert set(queues.split(",")) == required, path
    finally:
        app.close()
