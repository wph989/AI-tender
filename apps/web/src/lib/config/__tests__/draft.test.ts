/**
 * 配置草稿 → 提交补丁、文案口径（设计文档 08 第 2、5 节）。
 *
 * 断言的重点是"哪些 key 会被提交"：多提交一个 L2/L3 的 key 就会把版本送进门禁流程，
 * 少提交一个则表现为"改了没生效"，两者都不该靠人工点一遍页面才发现。
 */

import { describe, expect, it } from "vitest";

import {
  blockerLabel,
  buildPatch,
  diffRows,
  formatValue,
  impactKindLabel,
  itemsOfLayer,
  releaseStatusLabel,
} from "@/lib/config/draft";
import type { ConfigItem } from "@/types/config";

function item(overrides: Partial<ConfigItem> & { key: string }): ConfigItem {
  return {
    layer: "L1",
    value_type: "int",
    description: "",
    requires_gate: false,
    default: 0,
    value: 0,
    overridden: false,
    writable: true,
    ...overrides,
  };
}

const ITEMS: ConfigItem[] = [
  item({ key: "convert.max_inflight", value: 4 }),
  item({
    key: "mineru.tier",
    layer: "L2",
    value_type: "string",
    value: "standard",
  }),
  item({
    key: "llm_aided.title_leveling",
    layer: "L2",
    value_type: "bool",
    value: true,
  }),
  item({
    key: "mineru.output_formats",
    layer: "L2",
    value_type: "json",
    value: ["middle_json", "zip"],
  }),
  item({
    key: "extract.rerun.hide_threshold",
    layer: "L3",
    value_type: "number",
    value: 0.1,
  }),
];

describe("itemsOfLayer", () => {
  it("按层分组", () => {
    expect(itemsOfLayer(ITEMS, "L2").map((entry) => entry.key)).toEqual([
      "mineru.tier",
      "llm_aided.title_leveling",
      "mineru.output_formats",
    ]);
  });
});

describe("formatValue", () => {
  it("字符串不加引号、其余走 JSON", () => {
    expect(formatValue("standard")).toBe("standard");
    expect(formatValue(["middle_json", "zip"])).toBe('["middle_json","zip"]');
    expect(formatValue(true)).toBe("true");
    expect(formatValue(null)).toBe("");
  });
});

describe("buildPatch", () => {
  it("清空数值不能变成零并发或零阈值", () => {
    const result = buildPatch(ITEMS, {
      "convert.max_inflight": "",
      "extract.rerun.hide_threshold": "   ",
    });
    expect(result.patch).toEqual({});
    expect(result.errors).toEqual([
      "convert.max_inflight 不能为空",
      "extract.rerun.hide_threshold 不能为空",
    ]);
  });
  it("没改的项不进补丁", () => {
    const result = buildPatch(ITEMS, { "mineru.tier": "standard" });
    expect(result).toEqual({ patch: {}, errors: [] });
  });

  it("按类型转换后才提交", () => {
    const result = buildPatch(ITEMS, {
      "convert.max_inflight": "6",
      "llm_aided.title_leveling": "false",
      "mineru.output_formats": '["middle_json"]',
      "extract.rerun.hide_threshold": "0.2",
    });
    expect(result.errors).toEqual([]);
    expect(result.patch).toEqual({
      "convert.max_inflight": 6,
      "llm_aided.title_leveling": false,
      "mineru.output_formats": ["middle_json"],
      "extract.rerun.hide_threshold": 0.2,
    });
  });

  it("类型写错时不提交并给出可读原因", () => {
    const result = buildPatch(ITEMS, {
      "convert.max_inflight": "4.5",
      "mineru.output_formats": "middle_json",
    });
    expect(result.patch).toEqual({});
    expect(result.errors).toEqual([
      "convert.max_inflight 需要整数",
      "mineru.output_formats 不是合法 JSON",
    ]);
  });

  it("整数值相同但文本不同（4 与 4.0）不算变更", () => {
    expect(buildPatch(ITEMS, { "convert.max_inflight": "4.0" }).patch).toEqual(
      {},
    );
  });
});

describe("文案口径", () => {
  it("状态与影响清单种类都有中文说法", () => {
    expect(releaseStatusLabel("draft")).toBe("草稿");
    expect(releaseStatusLabel("active")).toBe("生效中");
    expect(impactKindLabel("regression_failure")).toBe("回归失败项");
  });

  it("门禁阻断码覆盖硬门槛与软门槛", () => {
    expect(blockerLabel("impact_not_acknowledged")).toBe(
      "变更影响清单还有未确认项",
    );
    expect(blockerLabel("first_pass_rate_drop_over_2pp")).toContain(
      "2 个百分点",
    );
    expect(blockerLabel("unknown_code")).toBe("unknown_code");
  });
});

describe("diffRows", () => {
  it("按 key 排序，页面刷新前后不跳动", () => {
    const rows = diffRows({
      "mineru.tier": { old: "standard", new: "basic" },
      "convert.max_inflight": { old: 4, new: 6 },
    });
    expect(rows.map((row) => row.key)).toEqual([
      "convert.max_inflight",
      "mineru.tier",
    ]);
  });
});
