"""验证先完整检索再逐条产出，业务 JSON 不依赖展示文本或原文存储。"""



from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.skills import skill_snapshot


def test_technical_skill_loads_adapted_category_rules_before_first_inference():
    loaded = load_module_skill(skill_snapshot(), "tech_requirement_parsing", categories=["goods"])
    assert "只输出两类内容：项目背景、技术方案要求" in loaded["model_rules"]
    assert "纯参数清单" in loaded["model_rules"]
    assert "安装调试、测试验证、迁移与运维方案" in loaded["model_rules"]
