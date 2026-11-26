"""问答核验按完整引文请求内复用，权限撤销后不能继承上次读取结果。"""

import copy
from unittest.mock import Mock

import pytest
from test_knowledge import block

from tender.application.knowledge.content import citation
from tender.application.knowledge.service import KnowledgeService


class AnswerStore:
    def __init__(self, *, with_items=True):
        self.ref = citation(block(), "投标人须具有甲级资质，不接受联合体。")
        self.with_items = with_items
        self.revoked = False
        self.calls = []
        self.other_ref = None

    def answer(self, answer_id):
        return {
            "id": answer_id, "project_id": 1, "collection_ids": [1],
            "items": [{"id": str(i), "field": "资质", "values": [{
                "value": "甲级资质", "citations": [copy.deepcopy(self.ref)],
            }]} for i in range(20)] if self.with_items else [],
            "relations": [{"subject": str(i), "citations": [
                copy.deepcopy(self.other_ref if self.other_ref and i == 19 else self.ref),
            ]} for i in range(20)],
        }

    def collections_for_project(self, project_id):
        return [1]

    def resolve(self, ref, *, with_content=False):
        self.calls.append((copy.deepcopy(ref), with_content))
        if self.revoked:
            raise LookupError("依据已撤销")
        return {**ref, "content": ref["quote"]} if with_content else dict(ref)


@pytest.mark.parametrize("with_items", [False, True])
def test_answer_reuses_verified_citation_and_rechecks_next_request(with_items):
    store = AnswerStore(with_items=with_items)
    service = KnowledgeService(store, 1, Mock(), Mock(), Mock())
    answer = service.get_answer(1)
    assert len(answer["relations"]) == 20 and len(store.calls) == 1
    assert store.calls[0][1] is with_items
    # 第二次读取必须重新核验；正文和关系都不能沿用上次的有效依据。
    store.revoked = True
    hidden = service.get_answer(1)
    assert len(store.calls) == 2 and hidden["relations"] == []
    assert all(not item["values"] and item["verification"] == "unavailable"
               for item in hidden["items"])


@pytest.mark.parametrize("identity", ["quote", "version_id", "page_no"])
def test_answer_does_not_reuse_another_complete_citation(identity):
    store = AnswerStore()
    store.other_ref = store.ref | {identity: "另一段原文" if identity == "quote" else 2}
    result = KnowledgeService(store, 1, Mock(), Mock(), Mock()).get_answer(1)
    assert len(result["relations"]) == 20 and len(store.calls) == 2
    assert store.calls[0][1] is True and store.calls[1][1] is False
