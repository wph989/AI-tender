"use client";

/**
 * 原文页上的角标气泡（见 docs/设计/06-前端展示与定位.md）。
 *
 * 只保留当前定位的角标，供用户回到刚才查看的结果；其他引用不铺满页面干扰原文。
 *
 * 为什么不做字符级文本高亮：那依赖文本层质量，扫描件根本没有文本层；
 * 角标只依赖 bbox，扫描件同样有效。
 *
 * 为什么单独成层而不并进 EvidenceLayer：那一层是 pointer-events-none 的纯绘制层，
 * 定位动画会重新挂载边框；角标单独保留，避免反向定位按钮因此丢失焦点。
 */

import type { Size } from "@/lib/coords/bbox";
import { bboxToRect } from "@/lib/coords/bbox";
import type { ActiveEvidence } from "@/lib/store/viewerStore";
import type { EvidenceItem } from "@/lib/viewer/evidenceIndex";

interface Props {
  pageNo: number;
  /** 本页画得出来的证据，带页内编号（见 lib/viewer/evidenceIndex.ts 的 badge）。 */
  items: readonly EvidenceItem[];
  activeEvidence: ActiveEvidence | null;
  /** null = 还没量到渲染尺寸，此时坐标算出来是错的，不画。 */
  viewport: Size | null;
  onLocate: (item: EvidenceItem) => void;
}

export function AnnotationLayer({ pageNo, items, activeEvidence, viewport, onLocate }: Props) {
  if (viewport === null || !activeEvidence || activeEvidence.pageNo !== pageNo) return null;

  // 同页可能有多个出处，角标与粗框只显示当前选中的原文块。
  // 多条摘录可以共享同一原文块；只保留当前选中证据的一个角标，避免重叠按钮。
  const activeItem = items.find((item) => item.evidenceId === activeEvidence.evidenceId
    && item.anchor === activeEvidence.anchor && item.pageNo === pageNo);
  const activeItems = activeItem ? [activeItem] : [];

  return (
    <div className="pointer-events-none absolute inset-0">
      {activeItems.map((item) => {
        const rect = bboxToRect(item.bbox, viewport);
        // 角标压在证据框左上角的外侧：压进框里会盖住被引用的那几个字，
        // 而那正是用户点开之前最想先看一眼的东西。
        const left = Math.max(0, rect.left - 9);
        const top = Math.max(0, rect.top - 9);
        return (
          <button
            key={`badge-${item.evidenceId}-${item.anchor}`}
            type="button"
            data-annotation-badge={item.badge}
            data-annotation-evidence={item.evidenceId}
            aria-label={"第 " + item.badge + " 处：" + item.label + "，跳到对应结果"}
            title={item.label + "：" + item.quote}
            onClick={() => onLocate(item)}
            style={{ left, top }}
            className={
              "pointer-events-auto absolute flex h-5 min-w-5 items-center justify-center " +
              "rounded-lg border px-0.5 font-mono text-[11px] leading-none tabular-nums " +
              "shadow-[0_1px_0_rgba(18,22,29,0.12)] transition-colors border-sky-600 bg-sky-600 text-white"
            }
          >
            {item.badge}
          </button>
        );
      })}
    </div>
  );
}
