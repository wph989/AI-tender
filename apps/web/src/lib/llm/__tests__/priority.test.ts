/**
 * 优先级重排的口径测试：这里算错会直接写坏线上路由顺序（1 级是首选模型），
 * 所以夹取、越界、非有限数三类边界都必须钉住。
 */
import { describe, expect, it } from "vitest";

import { moveToPriority } from "@/lib/llm/priority";

describe("moveToPriority", () => {
  it("上移：目标模型插到第 N 位，原第 N 位及其后顺延", () => {
    expect(moveToPriority([1, 2, 3], 3, 1)).toEqual([3, 1, 2]);
    expect(moveToPriority([1, 2, 3, 4], 4, 2)).toEqual([1, 4, 2, 3]);
  });

  it("下移：中间模型保持相对顺序", () => {
    expect(moveToPriority([1, 2, 3], 1, 3)).toEqual([2, 3, 1]);
    expect(moveToPriority([1, 2, 3, 4], 1, 3)).toEqual([2, 3, 1, 4]);
  });

  it("目标位置等于原位置时不改动顺序", () => {
    expect(moveToPriority([1, 2, 3], 2, 2)).toEqual([1, 2, 3]);
    expect(moveToPriority([1, 2, 3], 3, 3)).toEqual([1, 2, 3]);
  });

  it("越界夹到 1..N，不产生空洞", () => {
    expect(moveToPriority([1, 2, 3], 1, 99)).toEqual([2, 3, 1]);
    expect(moveToPriority([1, 2, 3], 3, 0)).toEqual([3, 1, 2]);
    expect(moveToPriority([1, 2, 3], 3, -5)).toEqual([3, 1, 2]);
  });

  it("非有限数按原位处理", () => {
    expect(moveToPriority([1, 2, 3], 2, Number.NaN)).toEqual([1, 2, 3]);
  });

  it("模型不在草稿里时返回等值副本，不修改入参", () => {
    const ids = [1, 2, 3];
    const moved = moveToPriority(ids, 9, 1);
    expect(moved).toEqual([1, 2, 3]);
    expect(moved).not.toBe(ids);
    expect(ids).toEqual([1, 2, 3]);
  });

  it("满 10 个绑定时仍可重排（上限与后端一致）", () => {
    const ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    expect(moveToPriority(ids, 10, 1)).toEqual([10, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });
});
