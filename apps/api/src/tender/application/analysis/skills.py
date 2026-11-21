"""专题名称及创建报告时冻结的 Skill 资源。"""

from pathlib import Path

from tender.domain.shared.digest import fingerprint

MODULES = {
    "project_basic_info_parsing": "项目概况",
    "disqualified_items_parsing": "否决条件",
    "biz_standard_parsing": "商务要求",
    "tech_requirement_parsing": "技术要求",
    "scoring_standard_parsing": "评分办法",
    "opening_requirement_parsing": "开标要求",
    "deposit_requirement_parsing": "保证金",
    "packaging_requirement_parsing": "封装与递交",
    "price_requirement_parsing": "报价要求",
    "company_performance_parsing": "业绩要求",
    "personnel_requirement_parsing": "人员要求",
    "bid_format_outline_parsing": "投标文件格式",
    "general_module_parsing": "补充发现与跨文件关联",
}
RESOURCE_ROOT = Path(__file__).resolve().parents[2] / "resources" / "parse_skills"

def skill_snapshot() -> dict[str, str]:
    # 公共工作方法和专题资源一起冻结；执行协议键由创建报告的用例另行写入。
    return {
        str(p.relative_to(RESOURCE_ROOT)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in sorted(RESOURCE_ROOT.rglob("*")) if p.suffix in {".md", ".json"}
    }


def skill_version(snapshot: dict | None = None) -> str:
    return fingerprint(snapshot or skill_snapshot())[:24]
