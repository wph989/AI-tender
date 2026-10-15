"""为真实图构造综合工具请求；检索阶段始终显式列在测试脚本中。"""

from test_deep_analysis import call

COMMON = {"kind": "common", "lot_refs": []}


def summary_record(key="warranty", text="质保期限为三年", quote="质保三年", **kwargs):
    return {
        "key": key, "kind": "requirement", "title": "质保期限", "group": "项目基本信息",
        "content": {"字段": "质保期限", "内容": text}, "scope": COMMON,
        "structuring": "complete",
        "citations": [{"block_id": "s1r1c0", "quote": quote}], **kwargs,
    }


def submission(records=(), *, coverage=(), gaps=(), final=True, summary="已综合全部已读条款"):
    return {
        "records": list(records), "coverage": list(coverage), "gaps": list(gaps),
        "research_summary": summary, "final": final,
    }


def research_done(topics=(), references=(), summary="已核对资料清单及主题检索范围"):
    return {"topics": list(topics), "references": list(references), "research_summary": summary}


def research_calls(*, query="质保", topics=(), references=()):
    return [
        call("list_documents", {}, "documents"),
        call("search_document", {"query": query}, "search"),
        call("complete_research", research_done(topics, references), "research"),
    ]


async def accept(items):
    for item in items:
        item["verification"] = "supported"


async def noop(*args):
    pass
