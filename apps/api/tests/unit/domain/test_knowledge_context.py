"""用碎标题、跨页条件和独立条款验证检索单元，不改变原文证据身份。"""

from tender.domain.knowledge.text import chunk_locations, iter_retrieval_chunks, split_elements


def elements(*texts):
    return [{"id": index + 1, "type": "text", "text": text, "page_no": index // 3 + 1}
            for index, text in enumerate(texts)]


def chunks(rows):
    return [chunk for _, chunk in iter_retrieval_chunks(rows)]


def test_fragmented_clause_keeps_title_value_condition_and_exception_together():
    rows = elements("第一章 招标公告", "5. 开标要求", "开标时间", "2026年11月16日10时",
                    "与投标截止同一时刻；仅限标段一。", "除另行通知外，迟到不予受理。",
                    "6. 联系方式", "联系电话：12345678")
    actual = chunks(rows)
    assert len(actual) == 2
    clause = actual[0]
    assert "仅限标段一" in clause["content"] and "除另行通知外" in clause["content"]
    assert "12345678" not in clause["content"]
    assert len(clause["content"].splitlines()) == 6


def test_original_block_identity_content_offsets_and_element_mapping_are_unchanged():
    rows = elements("第一章 招标公告", "开标时间", "正文" * 2000, "下一条款")
    original, actual = split_elements(rows), chunks(rows)
    assert "\n".join(r["content"] for r in actual) == "\n".join(r["content"] for r in original)
    assert {r["element_id"] for r in actual} <= {r["element_id"] for r in original}
    assert [row["ordinal"] for row in actual] == list(range(len(actual)))


def test_table_keeps_its_lead_in_and_all_cells_without_absorbing_next_matter():
    rows = elements("2.6 标段划分", "金额以以下表格为准：")
    rows.append({"id": 3, "type": "table", "html":
                 "<table><tr><td>标段一</td><td>1130万元</td></tr></table>"})
    rows.extend([{"id": 4, "type": "text", "text": "投标保证金6万元，不分标段。"}])
    actual = chunks(rows)
    assert len(actual) == 2
    assert "金额以以下表格为准" in actual[0]["content"]
    assert "1130万元" in actual[0]["content"]
    assert "保证金" not in actual[0]["content"]


def test_numbered_alternatives_and_new_chapters_do_not_share_context():
    actual = chunks(elements("第二章 投标人须知", "5.1 开标时间和地点（A）", "现场开标。",
                             "5.1 开标时间和地点（B）", "网上开标。",
                             "第三章 评标办法", "评分100分。"))
    assert "网上开标" not in actual[0]["content"]
    assert "现场开标" not in actual[1]["content"]
    assert "评分" not in actual[1]["content"]


def test_context_has_bounded_block_count_and_carries_numbered_section_for_continuations():
    actual = chunks(elements("1.1 服务要求", *[f"第{n}项条件" for n in range(35)]))
    assert all(len(row["content"].splitlines()) <= 12 for row in actual)
    assert all("1.1 服务要求" in row["chapter"] for row in actual)


def test_large_block_merges_real_coordinates_per_page_without_creating_small_evidence_ids():
    rows = elements("5. 开标要求", "现场开标。", "条件与例外。", "跨页继续说明。")
    for index, row in enumerate(rows):
        row.update(anchor=f'p{row["page_no"]}b{index + 1}', bbox_x0=0.1,
                   bbox_y0=index * 0.1, bbox_x1=0.8, bbox_y1=index * 0.1 + 0.05)
    grouped = chunks(rows)[0] | {"block_id": "s1r1g2c0"}
    places = chunk_locations(grouped)
    assert [p["page_no"] for p in places] == [1, 2]
    assert places[0]["bbox"] == [0.1, 0, 0.8, 0.25]
    assert {p["block_id"] for p in places} == {"s1r1g2c0"}
    assert all("locations" not in p for p in places)
