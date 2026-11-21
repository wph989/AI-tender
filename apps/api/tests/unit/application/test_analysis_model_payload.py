"""按真实工具请求验证模型负担精简，不以删减领域约束换取更短提示。"""



from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.skills import skill_snapshot


def test_custom_domain_constraints_under_generic_headings_are_retained():
    key = "project_basic_info_parsing"
    snapshot = skill_snapshot()
    snapshot[key + "/SKILL.md"] += (
        "\n## 适用场景\n禁止将代理机构地址作为项目地址。\n"
        "\n## 本项目的检索与输出\n只有采购人公告能够改变截止日期。\n"
        "\n## 新增业务限制\n预算与最高限价分别核对。\n"
    )
    skill = load_module_skill(snapshot, key)
    for rule in ("禁止将代理机构地址作为项目地址", "只有采购人公告能够改变截止日期",
                 "预算与最高限价分别核对"):
        assert rule in skill["model_rules"]
