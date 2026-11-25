"""在常规离线测试中检查真实装配，并证明类型检查没有将实现降级成 Any。"""

import os
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]


def _mypy(*paths: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        # 与统一入口一样直接读取实现签名，不依赖可能损坏的持久缓存。
        [sys.executable, "-m", "mypy", "--config-file", "pyproject.toml",
         "--no-incremental", "--cache-dir", os.devnull, *paths],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


def test_checker_reads_real_implementation_signatures(tmp_path):
    # 若把 follow_imports 从 silent 改成 skip，真实仓储会变成 Any，以下两处错误将漏报。
    fixture = tmp_path / "incompatible_port_probe.py"
    fixture.write_text(
        "from typing import Protocol\n"
        "from tender.adapters.pg.repositories.projects.projects import ProjectRepository\n"
        "class MissingOperation(Protocol):\n"
        "    def nonexistent_operation(self) -> None: ...\n"
        "class WrongSignature(Protocol):\n"
        "    def project(self, project_id: str) -> str: ...\n"
        "def missing(value: ProjectRepository) -> MissingOperation:\n"
        "    return value\n"
        "def incompatible(value: ProjectRepository) -> WrongSignature:\n"
        "    return value\n",
        encoding="utf-8",
    )
    result = _mypy(str(fixture))
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count("[return-value]") == 2, result.stdout + result.stderr
