/**
 * 结果面板六种形态的文案与徽标口径。
 *
 * 这六个状态是用户扫面板时的唯一信号：文案串了、配色重了，
 * 用户就会把「已驳回」当成「已确认」。样式断言故意比较去重后的数量，
 * 新增状态时忘了给独立配色会直接失败。
 */
import { describe, expect, it } from "vitest";

import {
  reviewActionLabel,
  statusBadgeClass,
  statusLabel,
  triggerLabel,
} from "@/lib/results/labels";
import type { ExtractionStatus } from "@/types/workbench";

const STATUSES: readonly ExtractionStatus[] = [
  "auto",
  "need_review",
  "verified",
  "rejected",
  "conflict",
  "not_found",
];

const UNKNOWN_CLASS = "border-slate-200 bg-slate-100 text-slate-600";

describe("结果状态文案", () => {
  it("六种状态各有中文名", () => {
    expect(STATUSES.map(statusLabel)).toEqual([
      "自动抽取",
      "待复核",
      "已确认",
      "已驳回",
      "存在冲突",
      "未找到",
    ]);
  });

  it("六种状态的徽标样式互不相同", () => {
    const classes = STATUSES.map(statusBadgeClass);
    expect(new Set(classes).size).toBe(STATUSES.length);
  });

  it("未知状态不假装认识：文案回退成原值，样式回退成中性", () => {
    expect(statusLabel("weird_state")).toBe("weird_state");
    expect(statusBadgeClass("weird_state")).toBe(UNKNOWN_CLASS);
  });
});

describe("尝试触发方式与复核动作文案", () => {
  it("机器重跑与人工修正分开命名", () => {
    expect(triggerLabel("first")).toBe("首次抽取");
    expect(triggerLabel("user_rerun")).toBe("重跑");
    expect(triggerLabel("hinted_rerun")).toBe("带提示重跑");
    expect(triggerLabel("manual_edit")).toBe("人工修正");
  });

  it("未知触发方式回退成原值，不吞掉信息", () => {
    expect(triggerLabel("param_rerun")).toBe("换参数重跑");
    expect(triggerLabel("brand_new")).toBe("brand_new");
  });

  it("没有复核动作时不编造文案", () => {
    expect(reviewActionLabel(null)).toBeNull();
    expect(reviewActionLabel(undefined)).toBeNull();
    expect(reviewActionLabel("supplement")).toBe("人工补充");
  });
});