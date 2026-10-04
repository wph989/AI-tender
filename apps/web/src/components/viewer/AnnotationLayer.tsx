"use client";

/**
 * 原文页上的角标气泡（见 docs/设计/06 第 11 节「页面内标注气泡」）。
 *
 * 为什么值得单独一层：评审人员的真实动作是「先扫原文，看见有标记的地方再点开」，
 * 而不是「先在右侧找字段、再跳到原文」。角标让原文本身变成一份带批注的稿子，
 * 把「结果」和「原文」在视觉上合成一件事。
 *
 * 为什么不做字符级文本高亮：那依赖文本层质量，扫描件根本没有文本层；
 * 角标只依赖 bbox，扫描件同样有效。
 *
 * 为什么单独成层而不并进 EvidenceLayer：那一层是 pointer-events-none 的纯绘制层，
 * 缩放时每帧重算全部矩形；角标是可点元素，混进去会让每次缩放都重挂一堆 button。
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
  if (viewport === null || items.length === 0) return null;

  return (
    <div className="pointer-events-none absolute inset-0">
      {items.map((item) => {
        // 判定用「锚点 + 页码」而不是 extractionId：同一条结果可能有多处证据，
        // 只有被点的那一处该亮（与 EvidenceLayer 同一口径）。
        const isActive =
          activeEvidence !== null &&
          activeEvidence.anchor === item.anchor &&
          activeEvidence.pageNo === pageNo;
        const rect = bboxToRect(item.bbox, viewport);
        // 角标压在证据框左上角的外侧：压进框里会盖住被引用的那几个字，
        // 而那正是用户点开之前最想先看一眼的东西。
        const left = Math.max(0, rect.left - 9);
        const top = Math.max(0, rect.top - 9);
        return (
          <button
            key={`badge-${item.extractionId}-${item.anchor}`}
            type="button"
            data-annotation-badge={item.badge}
            data-annotation-extraction={item.extractionId}
            aria-label={"第 " + item.badge + " 处：" + item.label + "，跳到对应结果"}
            title={item.label + "：" + item.quote}
            onClick={() => onLocate(item)}
            style={{ left, top }}
            className={
              "pointer-events-auto absolute flex h-5 min-w-5 items-center justify-center " +
              "rounded-lg border px-0.5 font-mono text-[11px] leading-none tabular-nums " +
              "shadow-[0_1px_0_rgba(18,22,29,0.12)] transition-colors " +
              (isActive
                ? "border-sky-600 bg-sky-600 text-white"
                : "border-slate-300 bg-white text-slate-600 hover:border-sky-500 hover:bg-sky-50 hover:text-slate-900")
            }
          >
            {item.badge}
          </button>
        );
      })}
    </div>
  );
}
