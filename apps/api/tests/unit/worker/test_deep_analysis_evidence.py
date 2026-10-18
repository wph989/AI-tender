"""校验窗口的证据扩展：引文块要能看到原文物理邻域，但引文本身仍限定已读块。"""

from __future__ import annotations

import asyncio

from tender.worker.analysis.controller import expand_evidence


def _block(offset: int, content: str, source_id: int = 13) -> dict:
    return {
        "block_id": f"s{source_id}r6c{offset}",
        "source_id": source_id,
        "parse_run_id": 6,
        "element_id": offset,
        "offset": offset,
        "page_no": 19 + offset // 50,
        "content": content,
    }


def test_expand_evidence_loads_neighbourhood_of_cited_sources_only() -> None:
    seen = {"s13r6c136": _block(136, "3.4.1 投标保证金 6万元整（不分标段）")}
    sources = [
        {"source_id": 13, "file_name": "招标文件.docx"},
        {"source_id": 9, "file_name": "别的资料.docx"},
    ]
    calls: list[int] = []

    async def read(source):
        calls.append(source["source_id"])
        return [
            _block(132, "投标人须知前附表"),
            _block(136, "3.4.1 投标保证金 6万元整（不分标段）"),
            _block(137, "3.5.3 近年完成的类似项目情况的时间要求 2020年1月1日以来"),
        ]

    items = [
        {
            "field": "投标保证金",
            "values": [
                {
                    "value": "投标人须知前附表3.4.1规定6万元整",
                    "citations": [
                        {
                            "block_id": "s13r6c136",
                            "quote": "3.4.1 投标保证金 6万元整（不分标段）",
                        }
                    ],
                }
            ],
        }
    ]
    evidence = asyncio.run(expand_evidence(items, seen=seen, sources=sources, read=read))
    # 只补读被引用资料，未引用的资料不能顺带读进来。
    assert calls == [13]
    assert "s13r6c132" in evidence and "s13r6c137" in evidence
    assert evidence["s13r6c136"]["content"].startswith("3.4.1")


def test_expand_evidence_falls_back_to_seen_when_source_unreadable() -> None:
    seen = {"s13r6c136": _block(136, "3.4.1 投标保证金")}

    async def read(source):
        raise RuntimeError("解析结果已失效")

    evidence = asyncio.run(
        expand_evidence(
            [
                {
                    "field": "保证金",
                    "values": [{"value": "6万元", "citations": [{"source_id": 13}]}],
                }
            ],
            seen=seen,
            sources=[{"source_id": 13, "file_name": "招标文件.docx"}],
            read=read,
        )
    )
    assert list(evidence) == ["s13r6c136"]
