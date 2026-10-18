"""项目用例：校验输入、决定 404，并整形项目详情。"""

from __future__ import annotations

from typing import Any

from tender.application.shared.errors import InvalidArgument, NotFound
from tender.ports.repository.projects.projects import ProjectRepository


class ProjectService:
    def __init__(self, repository: ProjectRepository, company_id: int) -> None:
        self.repository = repository

    def create(
        self,
        *,
        name: str,
        project_no: str | None,
        owner: str | None,
    ) -> dict[str, Any]:
        normalized = name.strip()
        if not normalized:
            raise InvalidArgument("项目名称不能为空")
        return self.repository.create(name=normalized, project_no=project_no, owner=owner)

    def list(self, *, offset: int, limit: int, keyword: str | None) -> dict[str, Any]:
        rows = self.repository.list(offset=offset, limit=limit, keyword=keyword)
        return {"items": rows, "offset": offset, "limit": limit}

    def detail(self, project_id: int) -> dict[str, Any]:
        project = self.repository.project(project_id)
        if project is None:
            raise NotFound("项目不存在")
        file_items = []
        for row in self.repository.files(project_id):
            item = dict(row)
            # 任务字段按列取回后在服务层组装，避免为了一个嵌套对象把 SQL 变成 JSON 拼接。
            job_id = item.pop("latest_job_id")
            job = {
                "id": job_id,
                "status": item.pop("latest_job_status"),
                "stage": item.pop("latest_job_stage"),
                "progress": item.pop("latest_job_progress"),
                "error_code": item.pop("latest_job_error_code"),
                "error_message": item.pop("latest_job_error_message"),
            }
            item["latest_job"] = None if job_id is None else job
            file_items.append(item)
        return {**project, "files": file_items, "lots": self.repository.lots(project_id)}

    def patch(self, project_id: int, changes: dict[str, object]) -> dict[str, Any]:
        if not changes:
            raise InvalidArgument("至少需要修改一个项目字段")
        values: dict[str, object] = {}
        for field in ("name", "project_no", "owner"):
            if field not in changes:
                continue
            value = changes[field]
            if field == "name":
                value = value.strip() if isinstance(value, str) else value
                if not value:
                    raise InvalidArgument("项目名称不能为空")
            values[field] = value
        if not self.repository.update(project_id, values):
            raise NotFound("项目不存在")
        return self.detail(project_id)

    def delete(self, project_id: int) -> None:
        if not self.repository.soft_delete(project_id):
            raise NotFound("项目不存在")
