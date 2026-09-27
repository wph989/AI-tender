/**
 * 页内精确滚动：把高亮块垂直居中（见 docs/设计/06 第 5 节第 ⑤ 步）。
 *
 * 为什么用几何计算而不是 scrollIntoView(高亮元素)：高亮元素要等 React 提交状态之后才存在，
 * 而这一步必须紧跟「写入高亮状态」执行——依赖渲染时机就会出现「有时居中、有时不居中」。
 * 这里只用两个矩形和容器滚动量做减法，结果可复现、可单测。
 */

import type { Bbox, Size } from "@/lib/coords/bbox";
import { bboxToRect } from "@/lib/coords/bbox";

export interface ScrollMetrics {
  /** 滚动容器 getBoundingClientRect().top（视口坐标系） */
  containerTop: number;
  /** 滚动容器当前 scrollTop */
  scrollTop: number;
  /** 滚动容器可视高度 clientHeight */
  clientHeight: number;
  /** 目标页容器 getBoundingClientRect().top（视口坐标系） */
  pageTop: number;
}

/** 目标 scrollTop（px），已做下界裁剪；调用方直接 scrollTo({ top, behavior: 'smooth' }) */
export function centerBboxScrollTop(metrics: ScrollMetrics, viewport: Size, bbox: Bbox): number {
  const rect = bboxToRect(bbox, viewport);
  // 页面在滚动内容中的位置 = 两者屏幕距离 + 当前滚动量
  const pageOffset = metrics.pageTop - metrics.containerTop + metrics.scrollTop;
  const center = pageOffset + rect.top + rect.height / 2;
  return Math.max(0, center - metrics.clientHeight / 2);
}