"use client";

/**
 * 高亮覆盖层——本系统的核心。
 *
 * 只为当前定位绘制一个粗边框，避免其他引用和重复框干扰阅读；内部始终透明。
 * 本切片不做文本 span 层（字符级高亮）：它依赖文本层质量，且扫描件没有文本层。
 *
 * 矩形全部由 `bbox × 视口尺寸` 得到（见 lib/coords/bbox.ts）。
 * 这一层不认识 PDF、不查询 DOM，只做乘法——所以缩放时它天然跟着变，
 * 定位时也不需要重新请求任何数据。
 *
 * `pageNo` 是必须的入参而不是可选优化：虚拟滚动会同时挂载上下各两屏的页面，
 * 不按页码过滤的话，当前高亮会被**每一页**都画一遍（同一组归一化坐标在不同页框里
 * 位置完全不同），表现为页面上同时出现好几个同形状的幽灵框。
 */

import type { Size } from "@/lib/coords/bbox";
import { bboxToRect } from "@/lib/coords/bbox";
import type { ActiveEvidence } from "@/lib/store/viewerStore";

interface Props {
  pageNo: number;
  activeEvidence: ActiveEvidence | null;
  pulseKey: number;
  /** null = 还没渲染出来，此时不画（画了也是错的位置） */
  viewport: Size | null;
}

export function EvidenceLayer({ pageNo, activeEvidence, pulseKey, viewport }: Props) {
  if (!viewport || !activeEvidence || activeEvidence.pageNo !== pageNo) return null;

  // 没有块坐标时保留页级定位；不在同屏挂载的其他页上复用当前坐标。
  const rect = activeEvidence.bbox ? bboxToRect(activeEvidence.bbox, viewport) : null;

  return (
    <div
      // key 带上 pulseKey：连续点同一条也会重新挂载，动画才会重放。
      key={`pulse-${pulseKey}-${activeEvidence.anchor}`}
      data-active-evidence
      data-active-anchor={activeEvidence.anchor}
      className={"evidence-pulse pointer-events-none absolute rounded-sm border-[3px] border-sky-700"
        + (rect ? "" : " inset-0 border-dashed")}
      style={rect ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height } : undefined}
    />
  );
}
