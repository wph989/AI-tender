/**
 * 标签页模型的口径测试：顺序、分组文案、计数。这里定错会让用户"在错误的标签里找字段"。
 */
import { describe, expect, it } from "vitest";

import { buildResultTabs } from "@/lib/results/grouping";
import type { ExtractionStatus, WireExtraction } from "@/types/workbench";

function makeExtraction(id: number, groupKey: string, status: ExtractionStatus = "auto"): WireExtraction {
  return {
    id,
    instance_id: id * 10,
    machine_attempt_no: 1,
    attempt_no: 1,
    trigger: "first",
    is_current: true,
    field_key: `f${id}`,
    group_key: groupKey,
    value_text: "值",
    confidence: 0.9,
    status,
    evidence_count: 0,
    evidence: [],
  };
}

describe("buildResultTabs", () => {
  it("按业务顺序排列，未知分组排最后且原样显示 key", () => {
    const tabs = buildResultTabs([
      makeExtraction(1, "risk"),
      makeExtraction(2, "custom_group"),
      makeExtraction(3, "basic_info"),
    ]);
    expect(tabs.map((tab) => tab.key)).toEqual(["basic_info", "risk", "custom_group"]);
    expect(tabs.map((tab) => tab.label)).toEqual(["基本信息", "风险条款", "custom_group"]);
  });

  it("待复核计数包含冲突，未找到单独计数", () => {
    const tabs = buildResultTabs([
      makeExtraction(1, "basic_info", "need_review"),
      makeExtraction(2, "basic_info", "conflict"),
      makeExtraction(3, "basic_info", "not_found"),
      makeExtraction(4, "basic_info", "auto"),
    ]);
    expect(tabs[0]?.pending).toBe(2);
    expect(tabs[0]?.notFound).toBe(1);
    expect(tabs[0]?.items).toHaveLength(4);
  });

  it("同组内保持接口给出的顺序", () => {
    const tabs = buildResultTabs([
      makeExtraction(7, "tech"),
      makeExtraction(3, "tech"),
      makeExtraction(5, "tech"),
    ]);
    expect(tabs[0]?.items.map((item) => item.id)).toEqual([7, 3, 5]);
  });

  it("空列表返回空数组，而不是一个空标签", () => {
    expect(buildResultTabs([])).toEqual([]);
  });
});