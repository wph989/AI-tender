/**
 * 页面几何的 TS 实现：视觉方向尺寸 = 应用 /Rotate 之后的尺寸（见 docs/设计/03-数据模型与溯源设计.md）。
 *
 * 前端用它算虚拟滚动的占位高度，必须与后端 domain/page.py 的换算完全一致：
 * 两者不一致时占位高度与真实渲染高度不符，滚动位置会在渲染完成的瞬间跳动。
 *
 * 注意前端**不做** bbox 的旋转换算：解析适配器输出的 bbox 已经是视觉方向，
 * 前端拿到后只按视口做乘法（见 10 第 4.5 节的分工说明）。
 */

import type { Size } from './bbox';

export interface PageGeometry {
  readonly pageNo: number;
  readonly widthPt: number;
  readonly heightPt: number;
  readonly rotation: number;
}

export function viewportSize(page: PageGeometry): Size {
  return page.rotation === 90 || page.rotation === 270
    ? { width: page.heightPt, height: page.widthPt }
    : { width: page.widthPt, height: page.heightPt };
}
