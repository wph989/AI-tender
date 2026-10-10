"""知识来源与任务快照的数据访问；所有入口先限定公司和仍有权访问的集合。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, text

from tender.application.knowledge import fingerprint


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def ensure_project_collection(connection: Any, project_id: int) -> int:
    return int(
        connection.execute(
            text("""
        INSERT INTO knowledge_collection (company_id, name, purpose, upload_project_id, is_project)
        SELECT company_id, name, 'tender', id, true FROM project WHERE id = :id
        ON CONFLICT (upload_project_id) DO UPDATE SET name = EXCLUDED.name
        RETURNING id"""),
            {"id": project_id},
        ).scalar_one()
    )


def sync_sources(connection: Any, project_id: int) -> None:
    connection.execute(
        text("""INSERT INTO knowledge_source (collection_id, project_file_id)
        SELECT k.id, f.id FROM knowledge_collection k
        JOIN project_file f ON f.project_id = k.upload_project_id
        WHERE f.project_id = :id AND f.deleted_at IS NULL
        ON CONFLICT (project_file_id) DO NOTHING"""),
        {"id": project_id},
    )


class KnowledgeStore:
    def __init__(self, engine: Engine, company_id: int) -> None:
        self.engine = engine
        self.company_id = company_id

    def rows(self, sql: str, params: dict | None = None) -> list[dict]:
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    text(sql), {**(params or {}), "company_id": self.company_id}
                ).mappings()
            ]

    def execute(self, sql: str, params: dict | None = None) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(sql), {**(params or {}), "company_id": self.company_id})

    def collection(self, collection_id: int) -> dict:
        rows = self.rows(
            """SELECT k.* FROM knowledge_collection k
            JOIN project p ON p.id = k.upload_project_id
            WHERE k.id = :id AND k.company_id = :company_id
              AND k.deleted_at IS NULL AND p.deleted_at IS NULL""",
            {"id": collection_id},
        )
        if not rows:
            raise LookupError("知识库不存在或已移除")
        return rows[0]

    def collections_for_project(self, project_id: int) -> list[int]:
        return [
            row["id"]
            for row in self.rows(
                """SELECT k.id FROM knowledge_collection k
            JOIN project p ON p.id = :project_id AND p.company_id = :company_id
            WHERE p.deleted_at IS NULL AND k.deleted_at IS NULL AND k.company_id = :company_id
              AND (k.upload_project_id = p.id OR EXISTS (
                SELECT 1 FROM project_knowledge_collection link
                WHERE link.project_id = p.id AND link.collection_id = k.id))""",
                {"project_id": project_id},
            )
        ]

    def sources(self, collection_ids: list[int]) -> list[dict]:
        return self.rows(
            """SELECT s.id AS source_id, k.id AS collection_id, k.purpose,
            p.id AS project_id, f.id AS project_file_id, f.display_name AS file_name,
            f.role, f.is_parseable, f.sha256, f.version_id,
            r.id AS parse_run_id, r.status AS parse_status,
            COALESCE(failure.error_message, r.error_message) AS error_message,
            r.page_count AS parsed_pages, v.page_count,
            active.id AS active_job_id, active.stage AS active_stage,
            failure.status AS processing_status,
            idx.id AS index_id, idx.status AS index_status, idx.embedding_signature,
            idx.embedding_model_id, idx.dimension, idx.error_message AS index_error
            FROM knowledge_source s JOIN knowledge_collection k ON k.id = s.collection_id
            JOIN project_file f ON f.id = s.project_file_id
            JOIN project p ON p.id = f.project_id
            LEFT JOIN document_version v ON v.id = f.version_id
            LEFT JOIN LATERAL (SELECT id, status, error_message, page_count FROM parse_run
                WHERE version_id = f.version_id ORDER BY created_at DESC, id DESC LIMIT 1) r ON true
            LEFT JOIN LATERAL (SELECT id, stage FROM job WHERE project_file_id = f.id
                AND stage IN ('probing','converting','submitting','parsing')
                AND status IN ('pending','running','submitting') AND finished_at IS NULL
                ORDER BY created_at DESC LIMIT 1) active ON true
            LEFT JOIN LATERAL (SELECT status,error_message FROM job
                WHERE project_file_id=f.id
                  AND stage IN ('probing','converting','submitting','parsing')
                ORDER BY created_at DESC,id DESC LIMIT 1) failure ON true
            LEFT JOIN LATERAL (SELECT * FROM knowledge_index
                WHERE source_id = s.id AND run_id = r.id ORDER BY id DESC LIMIT 1) idx ON true
            WHERE k.id = ANY(:ids) AND k.company_id = :company_id AND p.company_id = :company_id
                AND k.deleted_at IS NULL AND p.deleted_at IS NULL AND f.deleted_at IS NULL
                AND NOT EXISTS (SELECT 1 FROM project_file newer WHERE newer.replaces_id = f.id
                    AND newer.deleted_at IS NULL)
            ORDER BY f.sort_no, f.id""",
            {"ids": collection_ids},
        )

    def blocks(self, source: dict) -> list[dict]:
        rows = self.rows(
            """SELECT e.id, e.anchor, e.page_no, e.type, e.text, e.html,
            e.bbox_x0, e.bbox_y0, e.bbox_x1, e.bbox_y1
            FROM element e JOIN document_version v ON v.id = e.version_id
            JOIN project_file f ON f.id = :file_id AND f.version_id = v.id
            JOIN project p ON p.id = f.project_id
            JOIN knowledge_source s ON s.project_file_id = f.id AND s.id = :source_id
            JOIN knowledge_collection k ON k.id = s.collection_id
            WHERE e.version_id = :version_id AND e.run_id = :run_id
              AND p.company_id = :company_id AND k.company_id = :company_id
              AND f.deleted_at IS NULL AND p.deleted_at IS NULL AND k.deleted_at IS NULL
            ORDER BY e.page_no, e.order_no""",
            {
                "file_id": source["project_file_id"],
                "source_id": source["source_id"],
                "version_id": source["version_id"],
                "run_id": source["parse_run_id"],
            },
        )
        return rows

    def readable_chunks(self, source: dict) -> list[dict]:
        from tender.application.knowledge import split_elements

        elements = self.blocks(source)
        by_id = {element["id"]: element for element in elements}
        result = []
        for offset, chunk in enumerate(split_elements(elements)):
            element = by_id[chunk["element_id"]]
            values = [element[f"bbox_{axis}"] for axis in ("x0", "y0", "x1", "y1")]
            result.append(
                {
                    **source,
                    **chunk,
                    "offset": offset,
                    "block_id": f"s{source['source_id']}r{source['parse_run_id']}c{offset}",
                    "anchor": element["anchor"],
                    "page_no": element["page_no"],
                    "bbox": [float(v) for v in values]
                    if all(v is not None for v in values)
                    else None,
                }
            )
        return result

    def resolve(self, ref: dict, *, with_content: bool = False) -> dict:
        # 引文中的数字全部视作不可信输入，身份必须在一条带权限约束的查询中同时匹配。
        rows = self.rows(
            """SELECT e.id, e.page_no, e.anchor, e.text, e.html,
                e.bbox_x0, e.bbox_y0, e.bbox_x1, e.bbox_y1, f.display_name AS file_name
            FROM knowledge_source s JOIN knowledge_collection k ON k.id = s.collection_id
            JOIN project_file f ON f.id = s.project_file_id
            JOIN project p ON p.id = f.project_id
            JOIN element e ON e.version_id = :version_id AND e.run_id = :parse_run_id
            WHERE s.id = :source_id AND s.collection_id = :collection_id
              AND f.id = :project_file_id AND p.id = :project_id
              AND f.version_id = e.version_id AND e.id = :element_id AND e.anchor = :anchor
              AND k.company_id = :company_id AND p.company_id = :company_id
              AND k.deleted_at IS NULL AND f.deleted_at IS NULL AND p.deleted_at IS NULL""",
            ref,
        )
        if not rows:
            raise LookupError("引用原文已删除、撤销访问或与解析批次不符")
        row = rows[0]
        values = [row[f"bbox_{axis}"] for axis in ("x0", "y0", "x1", "y1")]
        resolved = {
            **ref,
            "page_no": row["page_no"],
            "file_name": row["file_name"],
            "bbox": [float(v) for v in values] if all(v is not None for v in values) else None,
        }
        if with_content:
            # 展示层要按元素原文回查值的位置，这里顺带返回，避免为同一权限再查一次。
            from tender.application.knowledge import plain_text

            resolved["content"] = plain_text(row)
        return resolved

    def embedding_config(self) -> dict | None:
        rows = self.rows("""SELECT m.id, m.model_id, m.timeout_seconds, p.base_url,
                m.config_revision, m.parameters, m.capabilities, m.embedding_space_id,
                p.protocol, m.api_mode, p.auth_mode,
                p.api_key_ciphertext FROM llm_feature_model fm
            JOIN llm_model m ON m.id = fm.model_id JOIN llm_provider p ON p.id = m.provider_id
            WHERE fm.feature_key = 'embedding' AND m.kind='embedding' AND m.enabled AND p.enabled
              AND m.deleted_at IS NULL AND p.deleted_at IS NULL ORDER BY fm.priority LIMIT 1""")
        if not rows:
            return None
        row = rows[0]
        # 同一注册行改模型名/服务地址也必须重建，不仅以数据库 id 判断嵌入空间。
        return row | {
            "signature": fingerprint(
                [
                    row["id"],
                    row["model_id"],
                    row["base_url"],
                    row["protocol"],
                    row["api_mode"],
                    row["embedding_space_id"],
                    row["parameters"],
                ]
            )
        }

    def rerank_config(self) -> dict | None:
        rows = self.rows("""SELECT m.*,p.base_url,p.auth_mode,p.api_key_ciphertext
            FROM llm_feature_model fm JOIN llm_model m ON m.id=fm.model_id
            JOIN llm_provider p ON p.id=m.provider_id
            WHERE fm.feature_key='rerank' AND m.kind='rerank' AND m.enabled AND p.enabled
              AND m.deleted_at IS NULL AND p.deleted_at IS NULL ORDER BY fm.priority LIMIT 1""")
        return rows[0] if rows else None


def source_state(source: dict) -> str:
    if not source["is_parseable"]:
        return "unsupported"
    if source.get("active_job_id"):
        return "processing"
    # 转换或提交失败可能尚无 parse_run，必须回显最新文件处理错误，不能一直显示待处理。
    if source.get("processing_status") in {"failed", "canceled"}:
        return "failed"
    if source.get("parse_status") == "completed":
        return "ready"
    if source.get("parse_status") == "partial":
        return "partial"
    if source.get("parse_status") in {"failed", "canceled"}:
        return "failed"
    return "pending"


def source_signature(sources: list[dict]) -> str:
    return fingerprint(
        [
            {k: row.get(k) for k in ("source_id", "version_id", "parse_run_id", "sha256", "role")}
            for row in sources
        ]
    )
