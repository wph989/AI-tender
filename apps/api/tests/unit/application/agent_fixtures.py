"""问答和专题 Agent 的离线模型响应与记录夹具。"""

from langchain_core.messages import AIMessage, message_to_dict

from tender.ports.llm.chat import Completion

KEY = "project_basic_info_parsing"


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


def raw(**overrides):
    return {"kind": "fact", "group": "项目基本信息", "content": {"字段": "质保", "内容": "三年"},
            "scope": {"kind": "common"}, "block_ids": ["s1r1c0"],
            **overrides}


def schema():
    return {"version": "1", "sections": [{"title": "项目基本信息", "layout": "table",
            "columns": ["字段", "内容"], "title_column": "字段"}]}


def summary_record(key="warranty", text="质保期限为三年", **kwargs):
    return {
        "key": key, "kind": "requirement", "title": "质保期限", "group": "项目基本信息",
        "content": {"字段": "质保期限", "内容": text},
        "scope": {"kind": "common", "lot_refs": []}, "structuring": "complete",
        "citations": [{"block_id": "s1r1c0"}], **kwargs,
    }


async def noop(*args):
    pass
