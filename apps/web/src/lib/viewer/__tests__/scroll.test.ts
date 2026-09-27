/**
 * 页内精确滚动的几何计算。之所以单独成函数并单测：它替代了 scrollIntoView(高亮元素)，
 * 而「有时居中、有时不居中」这种问题在浏览器里很难复现，只能靠算得对来保证。
 */
import { describe, expect, it } from "vitest";

import { centerBboxScrollTop } from "@/lib/viewer/scroll";

describe("centerBboxScrollTop", () => {
  it("把高亮块中心对齐到容器中线", () => {
    const top = centerBboxScrollTop(
      // 页面顶边在容器可视区上方（已滚过 200px，页面顶边在屏幕 100px 处）
      { containerTop: 0, scrollTop: 200, clientHeight: 1000, pageTop: 100 },
      { width: 800, height: 1000 },
      // 块中心 y = 0.51 → 页面内 510px
      [0.1, 0.5, 0.6, 0.52],
    );
    // pageOffset = 100 - 0 + 200 = 300；中心 300 + 510 = 810；减去半屏 500 → 310
    expect(top).toBeCloseTo(310, 9);
  });

  it("目标靠近内容顶部时不产生负滚动量", () => {
    const top = centerBboxScrollTop(
      { containerTop: 0, scrollTop: 0, clientHeight: 1000, pageTop: 0 },
      { width: 800, height: 1000 },
      [0.1, 0.01, 0.2, 0.03],
    );
    expect(top).toBe(0);
  });
});