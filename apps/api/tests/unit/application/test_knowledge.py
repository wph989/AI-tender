"""验证来源身份、检索回退与共用 JSON 纠正；避免只验证实现的字符串写法。"""

import asyncio

import pytest

from tender.application.analysis_skills import json_completion
from tender.application.knowledge import (
    cosine,
    fingerprint,
    merge_field_entries,
    rank_chunks,
    split_elements,
    validate_items,
)
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.domain.errors import (
    InvalidModelOutput,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
)
from tender.ports.llm import Completion


def block(source=1, text="投标人须具有甲级资质，不接受联合体。"):
    return {
        "block_id": f"s{source}r1c0",
        "source_id": source,
        "collection_id": source,
        "project_id": source,
        "project_file_id": source,
        "version_id": source,
        "parse_run_id": 1,
        "element_id": source,
        "anchor": "p1b1",
        "page_no": 1,
        "bbox": [0.1, 0.1, 0.8, 0.3],
        "file_name": f"文件{source}.pdf",
        "purpose": "tender",
        "content": text,
        "chapter": "资格条件",
        "offset": 0,
    }


def item(row):
    return {
        "field": "资格要求",
        "group": "资格条件",
        "sort_order": 0,
        "values": [
            {
                "value": row["content"],
                "citations": [{"block_id": row["block_id"], "quote": row["content"]}],
            }
        ],
        "note": "",
    }


def test_long_tables_are_fully_covered():
    content = "".join(f"第{i}项技术条件。" for i in range(2500))
    chunks = split_elements([{"id": 1, "type": "table", "html": "<table>" + content + "</table>"}])
    covered = set()
    for chunk in chunks:
        covered.update(range(chunk["char_start"], chunk["char_end"]))
    assert covered == set(range(len(" " + content + " ")))
    assert any("第2499项" in c["content"] for c in chunks)


def test_same_anchor_in_different_files_keeps_identity():
    a, b = block(1), block(2)
    items = validate_items([item(a), item(b)], {a["block_id"]: a, b["block_id"]: b})
    assert [i["values"][0]["citations"][0]["source_id"] for i in items] == [1, 2]
    first = items[0]["values"][0]["citations"][0]["version_id"]
    assert first != items[1]["values"][0]["citations"][0]["version_id"]


def test_unread_or_fabricated_quotes_are_rejected():
    row = block()
    with pytest.raises(ValueError, match="未读取"):
        validate_items([item(row)], {})
    bad = item(row)
    bad["values"][0]["citations"][0]["quote"] = "任何企业均可投标"
    with pytest.raises(ValueError, match="逐字"):
        validate_items([bad], {row["block_id"]: row})


def test_citation_is_realigned_to_the_value_it_supports():
    """定位必须是值本身出现的原文：同一块里的其它事实不能冒充依据。"""
    row = block(
        1,
        "招标人名称:中国通信工程有限公司。"
        + "投标人须自行核对资格条件。" * 3
        + "1.1.3  招标人地址  地址:浙江省杭州市滨江区滨安路1936号",
    )
    items = validate_items(
        [
            {
                "field": "招标人地址",
                "values": [
                    {
                        "value": "招标人地址:浙江省杭州市滨江区滨安路1936号",
                        "citations": [
                            {"block_id": row["block_id"],
                             "quote": "招标人名称:中国通信工程有限公司"}
                        ],
                    }
                ],
            }
        ],
        {row["block_id"]: row},
    )
    quote = items[0]["values"][0]["citations"][0]["quote"]
    assert "滨安路1936号" in quote and "招标人名称" not in quote
    # 收敛后的摘录必须仍是原文的逐字切片，不能变成重写过的句子。
    assert quote in row["content"]


def test_citation_moves_to_the_unique_block_that_contains_the_value():
    """本块确实没有该值时改引真实所在块，定位不能停留在无关摘录上。"""
    name_row = block(1, "招标人名称:中国通信工程有限公司") | {"block_id": "s1r1c0"}
    place_row = block(1, "1.1.5  项目建设地点  浙江省杭州市") | {
        "block_id": "s1r1c1",
        "element_id": 9,
    }
    items = validate_items(
        [
            {
                "field": "项目建设地点",
                "values": [
                    {
                        "value": "项目建设地点:浙江省杭州市",
                        "citations": [
                            {"block_id": "s1r1c0", "quote": "招标人名称:中国通信工程有限公司"}
                        ],
                    }
                ],
            }
        ],
        {row["block_id"]: row for row in (name_row, place_row)},
    )
    ref = items[0]["values"][0]["citations"][0]
    assert ref["block_id"] == "s1r1c1" and "浙江省杭州市" in ref["quote"]
    assert ref["quote"] in place_row["content"]


def test_table_citation_narrows_to_the_cell_that_holds_the_fact():
    """表格一行里写着多个事实：命中片段占值大半时摘录收窄到对应单元格。"""
    row = block(
        1,
        "标段序号  标段名称  预估监理费万元  中标份额\n"
        "一  杭州、嘉兴、湖州  1130  100%\n"
        "二  宁波、舟山、绍兴及省干传输、数据  400  100%",
    )
    items = validate_items(
        [
            {
                "field": "分标名称",
                "values": [
                    {
                        "value": "标段二：宁波、舟山、绍兴及省干传输、数据",
                        "citations": [
                            {"block_id": row["block_id"],
                             "quote": "一  杭州、嘉兴、湖州  1130  100%"}
                        ],
                    }
                ],
            }
        ],
        {row["block_id"]: row},
    )
    assert (
        items[0]["values"][0]["citations"][0]["quote"]
        == "宁波、舟山、绍兴及省干传输、数据"
    )


def test_citation_span_covers_every_fragment_of_a_compound_value():
    """值由多处原文组成时，摘录要覆盖各条，不能只截到标题那一句。"""
    row = block(
        1,
        "2.2.1 分值构成 资信业绩部分:见评标办法前附表 监理大纲部分:见评标办法前附表",
    )
    items = validate_items(
        [
            {
                "field": "分值构成",
                "values": [
                    {
                        "value": ("2.2.1 分值构成：（1）资信业绩部分:见评标办法前附表；"
                                  "（2）监理大纲部分:见评标办法前附表"),
                        "citations": [{"block_id": row["block_id"], "quote": "2.2.1 分值构成"}],
                    }
                ],
            }
        ],
        {row["block_id"]: row},
    )
    quote = items[0]["values"][0]["citations"][0]["quote"]
    assert "资信业绩部分" in quote and "监理大纲部分" in quote
    assert quote in row["content"]


def test_summary_value_without_原文_text_keeps_its_citation():
    """值本身是概括、原文没有对应文字时不做无法判定的改写，交给支持性校验。"""
    row = block(1, "标段一 杭州 1130；标段二 宁波 400")
    items = validate_items(
        [
            {
                "field": "分标规模",
                "values": [
                    {
                        "value": "两个标段合计1530万元",
                        "citations": [{"block_id": row["block_id"], "quote": "标段一 杭州 1130"}],
                    }
                ],
            }
        ],
        {row["block_id"]: row},
    )
    assert items[0]["values"][0]["citations"][0]["quote"] == "标段一 杭州 1130"


def test_same_value_and_location_are_deduped_within_a_field():
    """同一取值和同一处原文都只保留一条：重复行与重复定位不带来额外信息。"""
    row = block(1, "质保三年")
    reference = {"block_id": row["block_id"], "quote": "质保三年"}
    items = validate_items(
        [
            {
                "field": "质保期",
                "values": [
                    {"value": "质保三年", "citations": [reference]},
                    {"value": "质保 三年", "citations": [reference]},
                ],
            }
        ],
        {row["block_id"]: row},
    )
    assert len(items[0]["values"]) == 1
    assert len(items[0]["values"][0]["citations"]) == 1


def test_merge_field_entries_unions_values_and_locations():
    """同一字段的多个已核实版本合并成一行；未核实版本保持独立，不能被并进结果。"""

    def entry(order, pairs, verification="supported"):
        return {
            "id": "id" + str(order),
            "field": "质保期",
            "group": "质保",
            "sort_order": order,
            "values": [
                {
                    "value": value,
                    "citations": [
                        {
                            "block_id": block_id,
                            "source_id": 1,
                            # 不同块在原库里对应不同元素；位置去重按元素身份区分，
                            # 测试夹具必须照此建模，否则会被当成同一处原文合并。
                            "element_id": int(block_id.rsplit("c", 1)[-1]) + 1,
                            "page_no": 1,
                            "quote": quote,
                        }
                    ],
                }
                for value, block_id, quote in pairs
            ],
            "note": "第" + str(order) + "批",
            "verification": verification,
        }

    merged = merge_field_entries(
        [
            entry(1, [("质保三年", "s1r1c0", "质保三年")]),
            entry(
                2,
                [("质保三年", "s1r1c1", "质保三年。"), ("质保五年", "s1r1c1", "质保五年")],
            ),
            entry(3, [("质保六年", "s1r1c2", "质保六年")], verification="pending"),
        ]
    )
    assert len(merged) == 2
    row = next(entry for entry in merged if entry["verification"] == "supported")
    assert [value["value"] for value in row["values"]] == ["质保三年", "质保五年"]
    assert len(row["values"][0]["citations"]) == 2
    assert row["sort_order"] == 1
    assert row["id"] == fingerprint([row["field"], row["values"]])[:20]


def test_hybrid_retrieval_adds_semantic_match_without_keyword_match():
    rows = [
        {"content": "投标保证金", "embedding": [1.0, 0.0]},
        {"content": "应提供担保文件", "embedding": [0.9, 0.1]},
    ]
    assert len(rank_chunks(rows, "保证金")) == 1
    assert len(rank_chunks(rows, "保证金", [1.0, 0.0])) == 2
    with pytest.raises(ValueError, match="维度"):
        cosine([1.0], [1.0, 0.0])


def test_slow_search_embedding_falls_back_to_citable_fulltext_and_closes_client():
    row = block(text="历史设备质保期五年。")

    class Store:
        def embedding_config(self):
            return {"signature": "test-space"}

        def readable_chunks(self, source):
            return [row]

    class SlowEmbedding:
        canceled = False
        closed = False

        async def embed(self, texts):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.canceled = True
                raise

        async def aclose(self):
            self.closed = True

    async def run():
        client = SlowEmbedding()
        hits, info = await asyncio.wait_for(retrieve_chunks(
            Store(), [{"is_parseable": True, "parse_status": "completed"}], "质保期",
            lambda: None, lambda _: client, embedding_timeout=0.01,
        ), timeout=1)
        assert hits[0]["content"] == row["content"]
        assert hits[0]["anchor"] == row["anchor"]
        assert info["mode"] == "keyword" and info["semantic_source_ids"] == []
        assert "等待超时" in info["warning"]
        assert client.canceled and client.closed

    asyncio.run(run())




@pytest.mark.parametrize("first", ["需要读取补充通知", InvalidModelOutput("非法 JSON")])
def test_json_correction_states_the_structure_without_guessing_an_action(first):
    """结构错误只回传结构化纠正：不猜测自然语言动作，也不把未校验文本当作工具结果。"""
    prompts = []

    class Model:
        async def complete(self, prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                if isinstance(first, Exception):
                    raise first
                return Completion(first, "test")
            return Completion('{"action":"read","source_id":2}', "test")

    result = asyncio.run(json_completion(Model(), "执行模块"))
    assert result == {"action": "read", "source_id": 2}
    assert len(prompts) == 2
    assert "上次响应结构错误" in prompts[1] and "重新返回完整 JSON 对象" in prompts[1]
    assert "不能只说明计划" not in prompts[1]


def test_json_validation_runs_inside_the_correction_loop():
    """结构校验必须在重试循环内生效：先纠正具体问题，模型修正后立即接受。"""
    prompts = []
    answers = ['{"reviews":[]}', '{"reviews":[{"supported":true,"unsupported_claims":[]}]}']

    class Model:
        async def complete(self, prompt):
            prompts.append(prompt)
            return Completion(answers[len(prompts) - 1], "test")

    def validate(payload):
        reviews = payload.get("reviews")
        if not isinstance(reviews, list) or len(reviews) != 1:
            raise InvalidModelOutput("逐项断言审查 reviews 应有1条")
        if any("unsupported_claims" not in review for review in reviews):
            raise InvalidModelOutput("reviews 必须包含字符串数组 unsupported_claims")

    result = asyncio.run(json_completion(Model(), "校验", validate=validate))
    assert result == {"reviews": [{"supported": True, "unsupported_claims": []}]}
    assert len(prompts) == 2 and "逐项断言审查 reviews 应有1条" in prompts[1]


def test_truncated_output_is_not_retried_with_the_same_budget():
    """截断是输出上限问题，同一上限下重发无法收敛，直接上抛给提交工具指导拆分。"""
    calls = []

    class Model:
        async def complete(self, prompt):
            calls.append(prompt)
            raise ModelOutputTruncated("校验输出达到token上限")

    with pytest.raises(ModelOutputTruncated):
        asyncio.run(json_completion(Model(), "校验"))
    assert len(calls) == 1


def test_repeated_invalid_json_stops_after_two_corrections():
    calls = []

    class Model:
        async def complete(self, prompt):
            calls.append(prompt)
            return Completion("说明：{}", "test")

    with pytest.raises(InvalidModelOutput):
        asyncio.run(json_completion(Model(), "执行模块"))
    assert len(calls) == 3


@pytest.mark.parametrize(
    "error", [ModelUnavailable("超时"), ModelCallFailed("配置无效"), ModelRefused("拒绝")]
)
def test_json_correction_never_retries_connection_configuration_or_refusal(error):
    calls = []

    class Model:
        async def complete(self, prompt):
            calls.append(prompt)
            raise error

    with pytest.raises(type(error)):
        asyncio.run(json_completion(Model(), "执行模块"))
    assert len(calls) == 1
