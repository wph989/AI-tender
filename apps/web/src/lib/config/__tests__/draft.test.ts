/**
 * 配置草稿 → 提交补丁、文案口径（docs/质量/08-动态配置中心.md）。
 *
 * 断言的重点是"哪些 key 会被提交"：多提交一个 L2 的 key 就会把版本送进门禁流程，
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
  // 通用类型转换用独立样例键验证，避免测试依赖已经移除的业务配置。
  item({
    key: "sample.enabled",
    layer: "L2",
    value_type: "bool",
    value: true,
  }),
  item({
    key: "sample.formats",
    description: "示例格式",
    layer: "L2",
    value_type: "json",
    value: ["middle_json", "zip"],
  }),
  item({
    key: "sample.ratio",
    layer: "L1",
    value_type: "number",
    value: 0.1,
  }),
];

describe("itemsOfLayer", () => {
  it("按层分组", () => {
    expect(itemsOfLayer(ITEMS, "L2").map((entry) => entry.key)).toEqual([
      "mineru.tier",
      "sample.enabled",
      "sample.formats",
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
  it("校验服务端范围与枚举，未声明最大值时允许大预算", () => {
    const entries = [
      item({ key: "budget", minimum: 1 }),
      item({ key: "ratio", value_type: "number", minimum: 0, maximum: 1 }),
      item({ key: "mode", value_type: "string", choices: ["auto", "ocr"] }),
    ];
    expect(buildPatch(entries, { budget: "262144" })).toEqual({
      patch: { budget: 262144 }, errors: [],
    });
    expect(buildPatch(entries, { budget: "0", ratio: "1.1", mode: "unknown" })).toEqual({
      patch: {},
      errors: ["budget 超出允许范围", "ratio 超出允许范围", "mode 请选择支持的值"],
    });
  });

  it("只读项不能进入提交补丁", () => {
    expect(buildPatch([item({ key: "reserved", writable: false })], {
      reserved: "1",
    })).toEqual({ patch: {}, errors: ["reserved 当前不可修改"] });
  });

  it("清空数值不能变成零并发或零阈值", () => {
    const result = buildPatch(ITEMS, {
      "convert.max_inflight": "",
      "sample.ratio": "   ",
    });
    expect(result.patch).toEqual({});
    expect(result.errors).toEqual([
      "同时转换的文件数 不能为空",
      "sample.ratio 不能为空",
    ]);
  });
  it("没改的项不进补丁", () => {
    const result = buildPatch(ITEMS, { "mineru.tier": "standard" });
    expect(result).toEqual({ patch: {}, errors: [] });
  });

  it("按类型转换后才提交", () => {
    const result = buildPatch(ITEMS, {
      "convert.max_inflight": "6",
      "sample.enabled": "false",
      "sample.formats": '["middle_json"]',
      "sample.ratio": "0.2",
    });
    expect(result.errors).toEqual([]);
    expect(result.patch).toEqual({
      "convert.max_inflight": 6,
      "sample.enabled": false,
      "sample.formats": ["middle_json"],
      "sample.ratio": 0.2,
    });
  });

  it("类型写错时不提交并给出可读原因", () => {
    const result = buildPatch(ITEMS, {
      "convert.max_inflight": "4.5",
      "sample.formats": "middle_json",
    });
    expect(result.patch).toEqual({});
    expect(result.errors).toEqual([
      "同时转换的文件数 需要整数",
      "示例格式 不是合法 JSON",
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
    expect(impactKindLabel("config_changed")).toBe("配置项变更");
  });

  it("门禁显示未确认影响，未知错误保留可追踪代码", () => {
    expect(blockerLabel("impact_not_acknowledged")).toBe(
      "变更影响清单还有未确认项",
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
