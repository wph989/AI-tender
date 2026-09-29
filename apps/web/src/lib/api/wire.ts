/**
 * 线格式（snake_case）→ 内部模型（camelCase）的转换，全项目只此一处。
 *
 * 为什么要有这一层：接口字段名由后端冻结（见 docs/设计/05 第 7 节），
 * 内部坐标模型的字段名已经在共享向量里定死了。两边各改各的名字就会漂移，
 * 所以把差异集中在这里，而不是让 snake_case 渗进坐标库、或者让坐标库去迁就接口。
 */

import type { Bbox } from "@/lib/coords/bbox";
import { isValidBbox } from "@/lib/coords/bbox";
import type { PageGeometry } from "@/lib/coords/page";
import type { WirePageMeta } from "@/types/workbench";

export function toPageGeometry(page: WirePageMeta): PageGeometry {
  return {
    pageNo: page.page_no,
    widthPt: page.width_pt,
    heightPt: page.height_pt,
    rotation: page.rotation,
  };
}

/**
 * 校验来自接口的 bbox。
 *
 * 不合法时返回 null 而不是抛错：一条坏坐标不该让整页结果都渲染不出来，
 * 调用方按「仅页级定位」降级处理（见 docs/设计/06 第 5 节）。
 */
export function toBbox(raw: readonly number[] | null): Bbox | null {
  if (raw === null || raw.length !== 4) return null;
  const [x0, y0, x1, y1] = raw;
  if (x0 === undefined || y0 === undefined || x1 === undefined || y1 === undefined) return null;
  const bbox: Bbox = [x0, y0, x1, y1];
  return isValidBbox(bbox) ? bbox : null;
}

/**
 * 页面几何一致性断言：接口给的 pt 尺寸必须与 PDF.js 读出来的视口尺寸吻合（容差 1%）。
 *
 * 见 docs/设计/05 第 3.2 节：两者不一致说明「渲染基座」与「解析基座」错位，
 * 此时继续渲染高亮只会得到整体漂移的框，必须立刻告警而不是假装正常。
 */
export function assertViewportMatches(
  expected: { width: number; height: number },
  actual: { width: number; height: number },
  tolerance = 0.01,
): string | null {
  const ok = (a: number, b: number) => Math.abs(a - b) <= Math.max(a, b) * tolerance;
  if (ok(expected.width, actual.width) && ok(expected.height, actual.height)) return null;
  return (
    `渲染基座与解析基座尺寸不一致：接口 ${expected.width.toFixed(1)}×${expected.height.toFixed(1)}，` +
    `PDF.js ${actual.width.toFixed(1)}×${actual.height.toFixed(1)}。高亮位置不可信。`
  );
}