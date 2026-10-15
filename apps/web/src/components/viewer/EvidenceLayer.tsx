"use client";

/**
 * 高亮覆盖层——本系统的核心。
 *
 * 两层策略（见 docs/设计/06 第 4 节）：
 *  - 该页**所有**证据画淡色底框（始终绘制，只依赖归一化坐标，扫描件同样有效）；
 *  - 当前定位的那条画强色框并闪烁。
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

import type { EvidenceItem } from "@/lib/viewer/evidenceIndex";
import type { Size } from "@/lib/coords/bbox";
import { bboxToRect } from "@/lib/coords/bbox";
import type { ActiveEvidence } from "@/lib/store/viewerStore";

interface Props {
  pageNo: number;
  items: readonly EvidenceItem[];
  activeEvidence: ActiveEvidence | null;
  pulseKey: number;
  /** null = 还没渲染出来，此时不画（画了也是错的位置） */
  viewport: Size | null;
}

export function EvidenceLayer({ pageNo, items, activeEvidence, pulseKey, viewport }: Props) {
  if (!viewport) return null;

  // 只有「当前高亮落在本页」时才画强框；bbox 为 null 表示只有页级定位，改为整页边框闪一下
  const activeOnThisPage = activeEvidence !== null && activeEvidence.pageNo === pageNo;
  const activeBbox = activeOnThisPage ? activeEvidence.bbox : null;

  return (
    <div className="pointer-events-none absolute inset-0">
      {items.map((item) => {
        // 用「锚点 + 页码」而不是仅 evidenceId：同一条结果可能有多处证据甚至跨页，
        // 只有被点击的那一处该画强框（`p{page}b{block}` 是证据在 parse_run 内的唯一身份，见 03 第 2 节）
        const isActive =
          activeEvidence !== null &&
          activeEvidence.anchor === item.anchor &&
          activeEvidence.pageNo === item.pageNo;
        const rect = bboxToRect(item.bbox, viewport);
        return (
          <div
            key={`${item.evidenceId}-${item.anchor}`}
            data-evidence-id={item.evidenceId}
            data-evidence-anchor={item.anchor}
            className={
              isActive
                ? "absolute rounded-sm border-2 border-sky-500 bg-sky-300/40"
                : "absolute rounded-sm border border-sky-400/60 bg-sky-200/25"
            }
            style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
          />
        );
      })}

      {activeBbox !== null && activeEvidence !== null && (
        <div
          // key 带上 pulseKey：连续点同一条也会重新挂载，动画才会重放
          key={`pulse-${pulseKey}-${activeEvidence.anchor}`}
          data-active-evidence
          data-active-anchor={activeEvidence.anchor}
          className="evidence-pulse absolute rounded-sm border-2 border-sky-600 bg-sky-300/50 shadow-[0_0_0_3px_rgba(113,86,206,0.16)]"
          style={(() => {
            const rect = bboxToRect(activeBbox, viewport);
            return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
          })()}
        />
      )}

      {activeOnThisPage && activeBbox === null && (
        <div
          key={`page-${pulseKey}-${activeEvidence?.anchor ?? ""}`}
          data-active-evidence
          data-active-anchor={activeEvidence?.anchor ?? ""}
          className="evidence-pulse absolute inset-0 rounded-sm border-2 border-dashed border-sky-500"
        />
      )}
    </div>
  );
}
