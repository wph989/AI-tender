"""可控审查模型按当前包的真实事项归属回答核对方向，不能跨主题借用成果ID。"""

import json


def review_payload(prompt):
    # 审查指令可在原文后追加，测试模型按JSON请求行取值，不能假定最后一行总是正文。
    return json.loads(next(line for line in prompt.splitlines()
                           if line.startswith('{"protocol":')))


def applicability_proof(payload, block_ids):
    # 历史冻结包继续原格式；当前包的模型替身也须实际回答新增的适用性维度。
    return ({"applicability": {"status": "applicable", "reason": "已核对测试项目及条款适用条件",
                               "block_ids": block_ids}}
            if payload.get("require_applicability") else {})


def check_results(payload):
    results = {}
    records = {row["record_id"]: row for row in payload["records"]}
    delivered = [row["id"] for row in payload["evidence"] + payload["context_evidence"]]
    for item in payload.get("check_items", []):
        owners = {rid for group in payload["checks"]
                  if group.get("topic", payload.get("topic")) == item["topic"]
                  and group["scope"] == item["scope"]
                  for rid in group.get("record_ids", [])}
        ids = sorted(owners & records.keys())
        blocks = sorted({bid for rid in ids for bid in records[rid]["block_ids"]})
        results[item["check_id"]] = {
            "status": "covered" if ids else "not_required",
            "summary": "已按测试原文核对该方向，当前适用事项已列入成果" if ids else
                       "已核对测试资料，该方向未规定其它适用事项",
            "record_ids": ids, "block_ids": blocks or delivered[:1], "issue_indexes": [],
        }
    return results
