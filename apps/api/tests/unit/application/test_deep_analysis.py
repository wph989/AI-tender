"""用真实 DeepAgents 图验证权限、工具执行、纠正与 checkpoint 恢复。"""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, message_to_dict
from test_analysis_research import block

from tender.application.analysis.agent import split_absence_claims, validate_project_claims
from tender.application.analysis.skills import verify_items
from tender.application.knowledge.content import validate_items
from tender.domain.shared.errors import InvalidModelOutput
from tender.ports.llm.chat import Completion

KEY = "project_basic_info_parsing"
SKILL = {
    KEY
    + "/SKILL.md": (
        "---\nname: project-basic-info-parsing\ndescription: 分析概况\n---\n检索项目概况"
    ),
    KEY + "/references/output_format.md": (
        "```markdown\n## 项目基本信息\n| 字段 | 内容 |\n|---|---|\n```"
    ),
    KEY + "/references/coverage.json": "[]",
}


class ScriptedRouter:
    def __init__(self, calls):
        self.calls = list(calls)
        self.requests = []

    async def chat(self, messages, tools):
        self.requests.append((messages, tools))
        call = self.calls.pop(0)
        return Completion(
            content="",
            model="fixture",
            agent_message=message_to_dict(
                call if isinstance(call, AIMessage) else AIMessage(content="", tool_calls=[call])
            ),
        )


def call(name, args, number):
    if name == "submit_analysis":
        args = {"final": True, **args}
    return {"name": name, "args": args, "id": "call_" + str(number), "type": "tool_call"}


def submitted_field(field, value, quote="质保三年", block_id="s1r1c0"):
    """构造一条字段-值条目：field 是字段名，证据逐值绑定在 values 上。"""
    return {
        "field": field,
        "group": "",
        "sort_order": 0,
        "values": [{"value": value, "citations": [{"block_id": block_id, "quote": quote}]}],
        "note": "",
    }


@pytest.mark.parametrize(
    "title,text,refs",
    [
        ("条款未约定", "文件未约定违约金", [(10, 1, "质保三年")]),
        ("报价", "文件未明示税率", [(10, 1, "报价包含税费")]),
        ("限价", "未划分标段，全项目适用", [(10, 1, "最高限价78万元")]),
        ("历史建议", "本项目三年，历史五年", [(20, 2, "历史五年")]),
        ("交货期", "补充通知调整为45日", [(10, 2, "调整为45日")]),
    ],
)
def test_unsupported_absence_reference_only_and_one_sided_revision_are_rejected(title, text, refs):
    field = {
        "field": title,
        "values": [
            {
                "value": text,
                "citations": [{"project_id": p, "source_id": s, "quote": q} for p, s, q in refs],
            }
        ],
    }
    with pytest.raises(ValueError):
        validate_project_claims([field], 10)


def test_explicit_negative_requirement_and_two_sided_revision_are_accepted():
    validate_project_claims(
        [
            {
                "field": "职称",
                "values": [
                    {
                        "value": "不要求特定职称",
                        "citations": [
                            {"project_id": 10, "source_id": 1, "quote": "不要求特定职称"}
                        ],
                    }
                ],
            },
            {
                "field": "交货期",
                "values": [
                    {
                        "value": "补充通知调整为45日",
                        "citations": [
                            {"project_id": 10, "source_id": 1, "quote": "原交货期30日"},
                            {"project_id": 10, "source_id": 2, "quote": "调整为45日"},
                        ],
                    }
                ],
            },
        ],
        10,
    )


def test_revision_keeps_original_and_amendment_citations_after_alignment():
    """原条款用于证明修订前状态，不能因不含修订后的值就改引到补充文件。"""
    original = block() | {"content": "原交货期30日"}
    amendment = block(2, 10) | {"content": "补充通知调整为45日"}
    items = validate_items(
        [
            {
                "field": "交货期",
                "values": [
                    {
                        "value": "补充通知调整为45日",
                        "citations": [
                            {"block_id": row["block_id"], "quote": row["content"]}
                            for row in (original, amendment)
                        ],
                    }
                ],
            }
        ],
        {row["block_id"]: row for row in (original, amendment)},
    )
    validate_project_claims(items, 10)
    refs = items[0]["values"][0]["citations"]
    assert [(ref["source_id"], ref["quote"]) for ref in refs] == [
        (1, "原交货期30日"),
        (2, "补充通知调整为45日"),
    ]


def test_split_absence_claims_routes_gaps_and_keeps_scope_errors_strict():
    gap = {
        "field": "条款未约定",
        "values": [
            {
                "value": "文件未约定违约金",
                "citations": [{"project_id": 10, "source_id": 1, "quote": "质保三年"}],
            }
        ],
    }
    valid = {
        "field": "质保",
        "values": [
            {
                "value": "质保三年",
                "citations": [{"project_id": 10, "source_id": 1, "quote": "质保三年"}],
            }
        ],
    }
    reference_only = {
        "field": "历史",
        "values": [
            {
                "value": "历史五年",
                "citations": [{"project_id": 20, "source_id": 2, "quote": "历史五年"}],
            }
        ],
    }
    kept, gaps = split_absence_claims([gap, valid, reference_only], 10)
    assert gaps == [gap] and kept == [valid, reference_only]
    # 缺项目引用的条目不能借“缺口”之名绕开严格校验
    with pytest.raises(ValueError):
        validate_project_claims(kept, 10)


def test_support_review_rejects_unsupported_claim_even_when_model_flag_is_true():
    class Reviewer:
        async def complete(self, prompt):
            assert '"verification"' not in prompt
            return Completion(
                content=json.dumps(
                    {
                        "reviews": [
                            {
                                "supported": True,
                                "unsupported_claims": ["引文仅说明限价，不能证明全部标段适用"],
                            }
                        ]
                    }
                ),
                model="fixture",
            )

    item = {
        "field": "限价",
        "values": [
            {
                "value": "78万元，全部标段适用",
                "citations": [{"quote": "最高限价78万元"}],
            }
        ],
        "verification": "supported",
    }
    asyncio.run(verify_items(Reviewer(), [item], explain=True))
    assert item["verification"] == "unsupported"
    assert "全部标段" in item["verification_issues"][0]


@pytest.mark.parametrize(
    "note",
    [
        "供应商无需承担质保义务",
        "节点类型：材料章节；层级：2；上级路径：投标函",
    ],
)
def test_support_review_checks_claims_in_notes(note):
    class Reviewer:
        async def complete(self, prompt):
            payload = json.loads(prompt.rsplit("\n", 1)[-1])[0]
            # 正文值正确不能掩盖备注的免责断言或无依据的父级，校验器必须拿到备注。
            assert payload["note"] == note
            assert "note和group中的业务断言须由本字段的引用支持" in prompt
            return Completion(
                content=json.dumps(
                    {
                        "reviews": [
                            {
                                "supported": False,
                                "unsupported_claims": ["备注断言没有原文支持"],
                            }
                        ]
                    }
                ),
                model="fixture",
            )

    item = submitted_field("质保", "质保三年") | {"note": note}
    asyncio.run(verify_items(Reviewer(), [item], explain=True))
    assert item["verification"] == "unsupported"


@pytest.mark.parametrize(
    "result",
    [
        {"supported": [True]},
        {"reviews": [{"supported": True}]},
        {"reviews": [{"supported": True, "unsupported_claims": [None]}]},
    ],
)
def test_support_review_fails_closed_when_claim_review_is_missing(result):
    class Reviewer:
        async def complete(self, prompt):
            return Completion(content=json.dumps(result), model="fixture")

    with pytest.raises(InvalidModelOutput, match="逐项断言"):
        asyncio.run(verify_items(Reviewer(), [{"field": "限价", "values": []}], explain=True))


def test_support_review_batches_fields_without_mixing_their_verdicts():
    class Reviewer:
        def __init__(self):
            self.fields = []
            self.batches = []

        async def complete(self, prompt):
            batch = json.loads(prompt.rsplit("\n", 1)[-1])
            # 批量送审：一次请求覆盖至多3条，避免“字段数×提交轮次”次模型请求。
            assert 1 <= len(batch) <= 3
            self.batches.append(len(batch))
            self.fields.extend(item["field"] for item in batch)
            assert all("bbox" not in item["values"][0]["citations"][0] for item in batch)
            return Completion(
                content=json.dumps(
                    {
                        "reviews": [
                            {
                                "supported": item["field"] == "有据",
                                "unsupported_claims": []
                                if item["field"] == "有据"
                                else ["附加的适用范围无依据"],
                            }
                            for item in batch
                        ]
                    }
                ),
                model="fixture",
            )

    reviewer = Reviewer()
    items = [
        {
            "field": title,
            "values": [
                {
                    "value": "质保三年",
                    "citations": [{"quote": "质保三年", "bbox": [0, 0, 1, 1]}],
                }
            ],
        }
        for title in ("有据", "范围无据", "有据", "有据")
    ]
    asyncio.run(verify_items(reviewer, items, explain=True))
    # 4 条字段只发 2 次请求（3+1），逐条结论仍各自独立。
    assert reviewer.batches == [3, 1]
    assert reviewer.fields == ["有据", "范围无据", "有据", "有据"]
    assert [item["verification"] for item in items] == [
        "supported",
        "unsupported",
        "supported",
        "supported",
    ]


def test_support_review_receives_block_text_and_neighbours_for_section_attribution():
    """摘录看不到条号归属；校验必须拿到同块原文和邻近块，否则正确条款会被反复判无依据。"""

    class Reviewer:
        def __init__(self):
            self.batch = None

        async def complete(self, prompt):
            self.batch = json.loads(prompt.rsplit("\n", 1)[-1])
            return Completion(
                content=json.dumps({"reviews": [{"supported": True, "unsupported_claims": []}]}),
                model="fixture",
            )

    evidence = {
        f"c{offset}": {
            "block_id": f"c{offset}",
            "element_id": f"e{offset}",
            "source_id": 13,
            "parse_run_id": 6,
            "offset": offset,
            "page_no": 19,
            "chapter": "",
            "content": content,
        }
        for offset, content in (
            (131, "评标办法前附表"),
            (132, "投标人须知前附表"),
            (133, "1.4.1 投标人资质条件、能力、信誉 详见第一章3. 投标人资格要求"),
            (134, "1.4.2 是否接受联合体投标 ■不接受"),
        )
    }
    items = [
        {
            "field": "资质条件",
            "values": [
                {
                    "value": "通信工程监理资质乙级及以上（投标人须知前附表第1.4.1项）",
                    "citations": [
                        {
                            "block_id": "c133",
                            "quote": "1.4.1 投标人资质条件、能力、信誉",
                            "page_no": 19,
                            "bbox": [0, 0, 1, 1],
                        }
                    ],
                }
            ],
        },
        {
            # 旧 attempt 的引文没有块身份，必须仍能按元素和原文回查上下文。
            "field": "联合体",
            "values": [
                {
                    "value": "不接受联合体投标",
                    "citations": [
                        {
                            "source_id": 13,
                            "parse_run_id": 6,
                            "element_id": "e134",
                            "quote": "1.4.2 是否接受联合体投标 ■不接受",
                        }
                    ],
                }
            ],
        },
    ]
    reviewer = Reviewer()
    asyncio.run(verify_items(reviewer, items[:1], explain=True, evidence=evidence))
    assert items[0]["verification"] == "supported"
    citation = reviewer.batch[0]["values"][0]["citations"][0]
    assert "bbox" not in citation
    assert citation["page_no"] == 19
    context = citation["block_context"]
    assert context["offset"] == 133
    assert "投标人须知前附表" in json.dumps(context, ensure_ascii=False)
    assert [row["offset"] for row in context["before"]][-1] == 132
    assert [row["offset"] for row in context["after"]] == [134]
    legacy = Reviewer()
    asyncio.run(verify_items(legacy, items[1:], explain=True, evidence=evidence))
    legacy_citation = legacy.batch[0]["values"][0]["citations"][0]
    legacy_context = legacy_citation["block_context"]
    assert legacy_context["offset"] == 134
    assert "1.4.2 是否接受联合体投标" in legacy_context["block"]
    # 没有章节/条号归属的条目只带同块原文，不展开邻近块。
    assert "before" not in legacy_context and "after" not in legacy_context
    # 未传证据的调用（例如项目问答）保持原载荷，不能凭空出现上下文。
    plain = Reviewer()
    asyncio.run(verify_items(plain, items[:1], explain=True))
    assert "block_context" not in plain.batch[0]["values"][0]["citations"][0]


def _window_evidence(rows):
    return {
        f"c{offset}": {
            "block_id": f"c{offset}",
            "element_id": f"e{offset}",
            "source_id": 13,
            "parse_run_id": 6,
            "offset": offset,
            "page_no": page,
            "chapter": "",
            "content": content,
        }
        for offset, page, content in rows
    }


def test_support_review_receives_distant_chapter_heading_without_crossing_source_or_gaps():
    """真实人员条款距离章标题20块；扩大语义上下文仍须隔离资料、版本和缺块区间。"""
    from tender.application.analysis.skills import EvidenceWindows

    class Reviewer:
        async def complete(self, prompt):
            self.batch = json.loads(prompt.rsplit("\n", 1)[-1])
            return Completion(
                content=json.dumps({"reviews": [{"supported": True, "unsupported_claims": []}]}),
                model="fixture",
            )

    evidence = _window_evidence(
        [(15, 3, "第一章招标公告")]
        + [(offset, 4, "招标公告正文。") for offset in range(16, 35)]
        + [(35, 5, "3.5 安全生产管理人员须提供安全培训合格证书。")]
    )
    evidence["c19"]["content"] = "第二章 投标人须知........19"
    evidence["c22"]["content"] = "第三章评标办法规定了相关要求。"
    evidence["c25"]["content"] = "第四章合同条款 第五章委托人要求"
    for source_id, parse_run_id in ((14, 6), (13, 7)):
        evidence[f"foreign-{source_id}-{parse_run_id}"] = evidence["c15"] | {
            "block_id": f"foreign-{source_id}-{parse_run_id}",
            "source_id": source_id,
            "parse_run_id": parse_run_id,
            "offset": 34,
            "content": "第六章其他项目",
        }
    items = [
        {
            "field": "人员证书",
            "values": [
                {
                    "value": "第一章招标公告3.5要求安全生产管理人员提供安全培训合格证书。",
                    "citations": [{"block_id": "c35", "quote": evidence["c35"]["content"]}],
                }
            ],
        }
    ]
    reviewer = Reviewer()
    asyncio.run(verify_items(reviewer, items, explain=True, evidence=evidence))
    context = reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert context["chapter_heading"] == {
        "offset": 15,
        "page_no": 3,
        "content": "第一章招标公告",
    }
    assert all(row["offset"] > 15 for row in context["before"])
    # 已读块回退可能缺少中途出现的新章；这种情况下宁可不提供归属候选。
    sparse = {key: row for key, row in evidence.items() if key != "c28"}
    assert "chapter_heading" not in EvidenceWindows(sparse).context({"block_id": "c35"})
    evidence["c30"]["content"] = "第二章 投标人须知"
    newer = EvidenceWindows(evidence).context({"block_id": "c35"})
    assert newer["chapter_heading"]["offset"] == 30


def test_contract_section_heading_does_not_leak_into_next_chapter():
    """通用与专用合同条款的标题离条款很远，必须保留节归属并在新章边界清除。"""
    from tender.application.analysis.skills import EvidenceWindows

    evidence = _window_evidence([(n, 5, "合同正文。") for n in range(40)])
    for offset, content in (
        (0, "第四章合同条款及格式"),
        (1, "第一节通用合同条款"),
        (25, "第二节专用合同条款"),
        (35, "第五章委托人要求"),
    ):
        evidence[f"c{offset}"]["content"] = content
    windows = EvidenceWindows(evidence)
    assert windows.context({"block_id": "c20"})["section_heading"]["offset"] == 1
    assert windows.context({"block_id": "c30"})["section_heading"]["offset"] == 25
    later = windows.context({"block_id": "c39"})
    assert later["chapter_heading"]["offset"] == 35
    assert "section_heading" not in later


def test_support_review_merges_only_physically_adjacent_blocks_for_continuation():
    """同一句被分块切开时（“并应符合投标人”/“须知前附表的规定”）必须能合并阅读，
    但缺号的已读块不能拼进去，否则会把“相邻出现”误当原文依据。"""

    class Reviewer:
        def __init__(self):
            self.prompt = ""
            self.batch = None

        async def complete(self, prompt):
            self.prompt = prompt
            self.batch = json.loads(prompt.rsplit("\n", 1)[-1])
            return Completion(
                content=json.dumps({"reviews": [{"supported": True, "unsupported_claims": []}]}),
                model="fixture",
            )

    # c276 结尾没有句号，说明同一句延续到 c277；c275 是上一节的标题块。
    evidence = _window_evidence(
        (
            (275, 37, "3.4 投标保证金"),
            (
                276,
                37,
                "3.4.1 投标人在递交投标文件的同时应按投标人须知前附表规定的金额、"
                "形式递交，并应符合投标人",
            ),
            (277, 38, "须知前附表的 规定。"),
        )
    )
    items = [
        {
            "field": "联合体投标保证金递交",
            "values": [
                {
                    "value": (
                        "联合体投标的，其投标保证金可以由牵头人递交，"
                        "并应符合投标人须知前附表的规定。"
                    ),
                    "citations": [
                        {
                            "block_id": "c276",
                            "quote": "并应符合投标人",
                            "page_no": 37,
                            "bbox": [0, 0, 1, 1],
                        }
                    ],
                }
            ],
        }
    ]
    reviewer = Reviewer()
    asyncio.run(verify_items(reviewer, items, explain=True, evidence=evidence))
    assert items[0]["verification"] == "supported"
    context = reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert context["continuous"].startswith("〔块275〕")
    assert "〔引文块276〕" in context["continuous"]
    assert "须知前附表的 规定。" in context["continuous"]
    # 提示词必须把连续原文讲清楚，否则校验模型仍会把跨块续句判成无依据。
    assert "continuous" in reviewer.prompt and "跨块续句" in reviewer.prompt
    assert [row["offset"] for row in context["before"]] == [275]
    assert [row["offset"] for row in context["after"]] == [277]

    # 缺号时不能拼接：c136 之前只有 c132/c133 被读取，说明中间还有未读块。
    gap_evidence = _window_evidence(
        (
            (132, 19, "投标人须知前附表"),
            (133, 19, "1.1.2 招标人  招标人名称:中国通信工程有限公司"),
            (136, 22, "3.4.1 投标保证金  投标保证金金额:6万元整（不分标段）"),
        )
    )
    gap_items = [
        {
            "field": "投标保证金金额",
            "values": [
                {
                    "value": "投标人须知前附表3.4.1规定投标保证金金额6万元整（不分标段）。",
                    "citations": [
                        {
                            "block_id": "c136",
                            "quote": "3.4.1 投标保证金  投标保证金金额:6万元整（不分标段）",
                        }
                    ],
                }
            ],
        }
    ]
    gap_reviewer = Reviewer()
    asyncio.run(verify_items(gap_reviewer, gap_items, explain=True, evidence=gap_evidence))
    gap_context = gap_reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert "continuous" not in gap_context
    # 归属仍可由邻近标题块核对，标题块必须随载荷发出。
    assert [row["offset"] for row in gap_context["before"]] == [132, 133]
    assert "投标人须知前附表" in json.dumps(gap_context, ensure_ascii=False)

    # 前后块都已收句时不再拼接，避免把无关的上一段/下一段当成同一句续文。
    closed_evidence = _window_evidence(
        (
            (10, 5, "第二章 投标人须知。"),
            (11, 5, "投标人须知前附表第1.4.1项规定资质条件。"),
            (12, 5, "第一章 总则。"),
        )
    )
    closed_items = [
        {
            "field": "资质条件",
            "values": [
                {
                    "value": "投标人须知前附表第1.4.1项规定资质条件。",
                    "citations": [
                        {"block_id": "c11", "quote": "投标人须知前附表第1.4.1项规定资质条件。"}
                    ],
                }
            ],
        }
    ]
    closed_reviewer = Reviewer()
    asyncio.run(verify_items(closed_reviewer, closed_items, explain=True, evidence=closed_evidence))
    closed_context = closed_reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert "continuous" not in closed_context
