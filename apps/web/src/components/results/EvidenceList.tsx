"use client";

/**
 * 证据列表：一个结果可能从多处溯源而来（正文、前附表、附录，甚至跨页、后续还有跨文件）。
 *
 * 为什么逐条列出，而不是「证据 1/3 再点一次换下一个」：用户先要知道「一共有哪几处、
 * 分别在第几页」才能决定看哪一处；循环定位把选择权变成猜谜——点三次才轮到想看的那条。
 *
 * 为什么超过 3 条要折叠：个别字段（如废标条款）可能命中十几处，全铺开会把面板撑爆；
 * 「展开其余 N 处」把决定权交还给用户。
 *
 * 当前高亮项按「锚点」而不是 extractionId 判定：同一条结果的各处证据必须能区分，
 * 这与原文强框的口径一致（见 docs/设计/06 第 4 节）。
 */

import { useState } from "react";

import { DATA_CLASS } from "@/components/ui";
import type { EvidenceTarget } from "@/lib/viewer/evidenceIndex";

const COLLAPSE_AFTER = 3;

interface Props {
  targets: readonly EvidenceTarget[];
  /** 当前在原文里被强框高亮的证据锚点；null = 该结果未处于高亮状态 */
  activeAnchor: string | null;
  onLocate: (target: EvidenceTarget) => void;
}

export function EvidenceList({ targets, activeAnchor, onLocate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const hidden = targets.length - COLLAPSE_AFTER;
  const visible = expanded || hidden <= 0 ? targets : targets.slice(0, COLLAPSE_AFTER);

  return (
    <section className="mt-3 border-t border-slate-100 pt-2.5">
      <h5 className="mb-1.5 flex items-baseline gap-1.5 text-[13px] text-slate-400">
        <span>证据 {targets.length} 处</span>
        <span aria-hidden>·</span>
        <span>点击定位原文</span>
      </h5>
      <ul className="flex flex-col">
        {visible.map((target, index) => {
          const active = target.anchor === activeAnchor;
          // 表格引文可能包含 HTML 排版标记；预览只展示文字，锚点和提交原文仍保持原值。
          const preview = target.quote.replace(/<\/?(?:table|thead|tbody|tfoot|tr|th|td|p|div|span|br)\b[^>]*>/gi, " ").replace(/\s+/g, " ").trim();
          return (
            <li key={`${target.anchor}-${index}`}>
              <button
                type="button"
                data-evidence-row
                data-evidence-anchor={target.anchor}
                onClick={() => onLocate(target)}
                title={preview || undefined}
                className={
                  "relative mb-1.5 flex w-full items-center gap-2 rounded-lg border border-sky-100 px-2.5 py-2 text-left text-[12px] " +
                  (active ? "bg-sky-100" : "bg-sky-50/50 hover:bg-sky-50")
                }
              >
                {active && (
                  <span aria-hidden className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-sky-400" />
                )}
                <span className={DATA_CLASS + " w-3 shrink-0 text-[13px] text-slate-400"}>
                  {index + 1}
                </span>
                <span
                  className={
                    DATA_CLASS +
                    " shrink-0 rounded bg-white px-1.5 py-0.5 text-[11px] text-slate-500"
                  }
                >
                  第 {target.pageNo} 页
                </span>
                {target.bbox === null && (
                  <span className="shrink-0 text-[11px] text-slate-400">页级</span>
                )}
                <span className="min-w-0 flex-1 truncate text-slate-600">
                  {preview || "（无引文）"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-1.5 text-[13px] text-sky-700 hover:underline"
        >
          {expanded ? "收起" : `展开其余 ${hidden} 处`}
        </button>
      )}
    </section>
  );
}
