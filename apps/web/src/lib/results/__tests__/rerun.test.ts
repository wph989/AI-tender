import { describe, expect, it } from "vitest";

import { rerunMode, rerunModeByField } from "@/lib/results/rerun";

describe("rerunModeByField", () => {
  it("按 field_key 映射服务端下发的三种模式", () => {
    const modes = rerunModeByField([
      { field_key: "bid_bond_amount", rerun_button: "hide" },
      { field_key: "budget_amount", rerun_button: "show_hint" },
      { field_key: "tender_no", rerun_button: "show" },
    ]);
    expect(modes).toEqual({
      bid_bond_amount: "hide",
      budget_amount: "show_hint",
      tender_no: "show",
    });
  });

  it("未知模式与空 field_key 都不落进映射表", () => {
    const modes = rerunModeByField([
      { field_key: "a_field", rerun_button: "whatever" },
      { field_key: "", rerun_button: "hide" },
    ]);
    expect(modes).toEqual({ a_field: "show" });
  });

  it("没有统计的字段回落 show：取数失败不能把重跑入口藏掉", () => {
    expect(rerunMode({}, "unknown_field")).toBe("show");
  });
});