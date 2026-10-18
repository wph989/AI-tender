"""路由与设计文档的接口清单一致性（防漂移）。

权威是 `docs/设计/05-后端API设计.md` 第 2 节的冻结清单，代码只是它的实现：
清单里列了但没实现的接口、代码里加了却没上清单的接口，都会在这里变红。

两张例外表都要写理由，并且有断言盯着它们别过期：
`_PLANNED` 里的接口一旦实现就必须删，「顺手加的接口」进 `_UNDOCUMENTED` 前要先想清楚。
"""

from __future__ import annotations

import re
from pathlib import Path

from tender.api.analysis import routes as analysis_api
from tender.api.configuration import routes as config
from tender.api.documents import parsing, versions
from tender.api.jobs import routes as jobs
from tender.api.knowledge import routes as knowledge
from tender.api.llm import routes as llm
from tender.api.projects import files as project_files
from tender.api.projects import routes as projects

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOC = _REPO_ROOT / "docs" / "设计" / "05-后端API设计.md"

_ROW_RE = re.compile(r"^\|\s*`(GET|POST|PATCH|PUT|DELETE)`\s*\|\s*`(/api/v1/[^`]+)`", re.M)
_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")

# 清单里没有但要保留的接口：写明为什么，别让它们变成第二份事实源。
_UNDOCUMENTED = {
    "GET /api/v1/versions/{}/elements": "工作台一次拉全量块建证据索引；清单只列了按页拉取",
    "GET /api/v1/projects/{}/files/{}/original": "单个上传件原件下载；05 §3.1 只写了签名 URL 原则",
}

# 已进清单、代码还没写的接口（阶段 3 已完成，表留空以防下一阶段再加）。
_PLANNED: dict[str, str] = {}


def _normalize(path: str) -> str:
    """路径参数名不参与比对（vid / version_id 是同一个参数），查询串也去掉。"""
    return _PLACEHOLDER_RE.sub("{}", path.split("?", 1)[0].rstrip("/"))


def _documented() -> set[str]:
    text = _DOC.read_text(encoding="utf-8")
    return {f"{method} {_normalize(path)}" for method, path in _ROW_RE.findall(text)}


def _implemented() -> set[str]:
    routers = (
        config.router,
        projects.router,
        project_files.router,
        versions.router,
        parsing.router,
        jobs.router,
        knowledge.router,
        analysis_api.router,
        llm.router,
    )
    found: set[str] = set()
    for router in routers:
        for route in router.routes:
            for method in sorted(getattr(route, "methods", None) or []):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                found.add(f"{method} {_normalize(route.path)}")
    return found


def _missing() -> set[str]:
    return _documented() - _implemented()


def test_doc_list_is_parsed() -> None:
    """解析器静默失效比漂移更危险：清单改了写法而解析不到时必须先红在这里。"""
    assert len(_documented()) >= 40


def test_every_documented_route_is_implemented() -> None:
    unexpected = sorted(_missing() - set(_PLANNED))
    assert not unexpected, f"清单里列了但没实现的接口：{unexpected}"


def test_planned_routes_are_still_missing() -> None:
    """已经实现的接口要从 _PLANNED 删掉，否则这张表会慢慢变成谎话。"""
    stale = sorted(set(_PLANNED) - _missing())
    assert not stale, f"这些接口已经实现，请从 _PLANNED 删除：{stale}"


def test_implemented_routes_are_documented_or_explained() -> None:
    unexplained = sorted(
        item for item in _implemented() - _documented() if item not in _UNDOCUMENTED
    )
    assert not unexplained, (
        f"代码里有、清单里没有的接口（补清单或写进 _UNDOCUMENTED）：{unexplained}"
    )
