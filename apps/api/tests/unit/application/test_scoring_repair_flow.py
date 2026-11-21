"""评分修复须保留可靠成果；未知分值和未展开转引不能变成正式评分条款。"""


import pytest
from agent_fixtures import submitted_field
from test_analysis_research import block

from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.skills import skill_snapshot
from tender.application.knowledge.content import validate_items

KEY = "scoring_standard_parsing"
SNAPSHOT = skill_snapshot() | {KEY + "/references/coverage.json": "[]"}
METHOD = "采用综合评分法"


def test_original_formula_quote_survives_a_plain_display_formula():
    quote = r"投标人得分=\mathbf{A}+\mathbf{B}+\mathbf{C}+\mathbf{D}"
    row = block() | {"content": quote}
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field("总分计算公式", "投标人得分=A+B+C+D", quote=quote)],
                           evidence)
    assert items[0]["values"][0]["value"] == "投标人得分=A+B+C+D"
    assert items[0]["values"][0]["citations"][0]["quote"] == quote


def test_domain_rules_are_loaded_for_selected_categories_without_defaulting_to_service():
    snapshot = {
        KEY + "/SKILL.md": "按本专题业务边界解析评分",
        KEY + "/references/output_format.md": "评分输出模板",
        **{KEY + "/references/" + category + "/extraction_rules.md": category + "专属细则"
           for category in ("service", "goods", "engineering")},
    }
    loaded = load_module_skill(snapshot, KEY, categories=("goods", "engineering", "goods"))
    assert "goods专属细则" in loaded["model_rules"]
    assert "engineering专属细则" in loaded["model_rules"]
    assert "service专属细则" not in loaded["model_rules"]
    assert loaded["model_rules"].count("goods专属细则") == 1
    assert "专属细则" not in load_module_skill(snapshot, KEY)["model_rules"]


@pytest.mark.parametrize("key,paths", [
    ("project_basic_info_parsing", ["references/extraction_rules.md"]),
    ("bid_format_outline_parsing", [
        "references/locate_rules.md", "references/outline_extract_rules.md",
    ]),
])
def test_required_domain_references_are_loaded_before_analysis(key, paths):
    snapshot = {key + "/SKILL.md": "主规则", **{key + "/" + p: p for p in paths}}
    loaded = load_module_skill(snapshot, key)
    assert all(p in loaded["model_rules"] for p in paths)
