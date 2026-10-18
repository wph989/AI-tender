"""职责定义必须映射到现有架构，防止再次增加同义层或绕过仓储端口。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src" / "tender"


def _imports(directory: str) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for path in (ROOT / directory).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                result.update((str(path.relative_to(ROOT)), alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                # 相对导入也必须检查，否则换一种写法就能绕过边界。
                package = ["tender", *path.relative_to(ROOT).parts[:-1]]
                if node.level:
                    package = package[: len(package) - node.level + 1]
                    module = ".".join(package + ([node.module] if node.module else []))
                else:
                    module = node.module or ""
                result.add((str(path.relative_to(ROOT)), module))
                result.update(
                    (str(path.relative_to(ROOT)), f"{module}.{alias.name}") for alias in node.names
                )
    return result


@pytest.mark.parametrize("name", ["services", "service", "crud", "agent"])
def test_no_parallel_responsibility_directories(name: str) -> None:
    # service/crud/agent 表示职责；现有 application、ports、adapters 已有对应位置。
    assert not (ROOT / name).exists(), f"请按 docs/工程/21-后端文件树与放置规则.md 放置 {name}"


@pytest.mark.parametrize(
    ("directory", "forbidden"),
    [
        ("api", ("tender.adapters", "tender.worker", "sqlalchemy")),
        # Worker 可以调用外部服务适配器，但数据库与检查点设施必须从装配点取得。
        (
            "worker",
            (
                "tender.adapters.pg", "tender.config.registry",
                "tender.config.snapshot", "sqlalchemy",
            ),
        ),
        (
            "application",
            (
                "tender.api",
                "tender.adapters",
                "tender.worker",
                "tender.core.di",
                "tender.config.registry",
                "tender.config.snapshot",
                "sqlalchemy",
            ),
        ),
        (
            "ports",
            ("tender.api", "tender.application", "tender.adapters", "tender.worker", "sqlalchemy"),
        ),
    ],
)
def test_no_direct_dependency_on_implementations(
    directory: str, forbidden: tuple[str, ...]
) -> None:
    # 装配点允许知道实现；入口只调用装配函数，用例通过注入的端口执行。
    violations = [
        f"{filename} -> {module}"
        for filename, module in sorted(_imports(directory))
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden)
        # 既有全局错误边界把完整性异常映射为 HTTP；它不执行 SQL，也不构造数据库依赖。
        and not (
            filename.replace("\\", "/") == "api/shared/errors.py"
            and module in {"sqlalchemy.exc", "sqlalchemy.exc.IntegrityError"}
        )
    ]
    assert violations == []


@pytest.mark.parametrize(
    ("directory", "infrastructure"),
    [
        ("api", {"app.py"}),
        ("application", set()),
        ("ports", set()),
        ("ports/repository", set()),
        ("adapters", set()),
        ("adapters/pg/repositories", set()),
        ("domain", set()),
        ("worker", {"celery_app.py", "dispatch.py", "logging.py"}),
    ],
)
def test_business_files_live_in_business_packages(directory, infrastructure):
    # 即使只有一个文件，已确定的业务也有稳定归属；根目录只保留明确的技术入口。
    unexpected = {
        path.name for path in (ROOT / directory).glob("*.py")
        if path.name != "__init__.py" and path.name not in infrastructure
    }
    assert unexpected == set(), f"{directory} 中的业务文件需要归组：{unexpected}"


@pytest.mark.parametrize(
    "directory", ["api", "application", "ports/repository", "adapters/pg/repositories"]
)
def test_business_names_are_consistent_across_layers(directory):
    expected = {"projects", "documents", "knowledge", "analysis", "llm", "configuration", "jobs"}
    actual = {path.name for path in (ROOT / directory).iterdir() if path.is_dir()}
    assert expected <= actual
