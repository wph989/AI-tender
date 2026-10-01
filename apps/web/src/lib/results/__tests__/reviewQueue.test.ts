/**
 * 复核队列的排序口径：冲突必须排第一、未找到必须排最后。
 * 这两条是「点开复核就能看到该看的东西」的全部保证，顺序错了这个视图就没有意义。
 */
import { describe, expect, it } from "vitest";

import { needsActionCount, orderForReview } from "@/lib/results/reviewQueue";
import type { ExtractionStatus, WireExtraction } from "@/types/workbench";

function item(id: number, status: ExtractionStatus): WireExtraction {
  return {
    id,
    instance_id: id * 10,
    machine_attempt_no: 1,
    attempt_no: 1,
    trigger: "first",
    is_current: true,
    field_key: "field_" + id,
    group_key: "basic_info",
    value_text: "值",
    confidence: 0.5,
    status,
    evidence_count: 0,
    evidence: [],
  };
}

describe("orderForReview", () => {
  it("冲突在前、待复核其次、未找到垫底", () => {
    const ordered = orderForReview([
      item(1, "not_found"),
      item(2, "auto"),
      item(3, "need_review"),
      item(4, "conflict"),
      item(5, "verified"),
    ]);
    expect(ordered.map((entry) => entry.id)).toEqual([4, 3, 2, 5, 1]);
  });

  it("同优先级保持接口顺序：重跑后不会整屏乱跳", () => {
    const ordered = orderForReview([item(1, "need_review"), item(2, "need_review")]);
    expect(ordered.map((entry) => entry.id)).toEqual([1, 2]);
  });

  it("不改动入参数组（排序结果要能直接当渲染输入）", () => {
    const source = [item(1, "not_found"), item(2, "conflict")];
    orderForReview(source);
    expect(source.map((entry) => entry.id)).toEqual([1, 2]);
  });
});

describe("needsActionCount", () => {
  it("只数冲突与待复核：自动档不算「要你来看」", () => {
    expect(
      needsActionCount([
        item(1, "conflict"),
        item(2, "need_review"),
        item(3, "auto"),
        item(4, "verified"),
        item(5, "not_found"),
      ]),
    ).toBe(2);
  });
});
