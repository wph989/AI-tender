"use client";

/**
 * 结果面板：按分组列出字段结果，顶部给复核进度概览（见 docs/设计/06 第 2 / 11 节）。
 *
 * 分组顺序按业务重要性固定，不按接口返回顺序：接口顺序是抽取顺序，用户核对顺序是业务顺序。
 * 未知分组排在最后并原样显示 key，避免新分组悄悄排到首位抢注意力。
 */

import type { EvidenceIndex, EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireExtraction } from "@/types/workbench";

import { ResultCard } from "./ResultCard";

const GROUP_LABELS: Record<string, string> = {
  basic_info: "基本信息",
  qualification: "资格要求",
  scoring: "评分办法",
  commercial: "商务条款",
  tech: "技术要求",
  risk: "风险条款",
};

const GROUP_ORDER = ["basic_info", "qualification", "scoring", "commercial", "tech", "risk"];

const NO_TARGETS: readonly EvidenceTarget[] = [];

function groupRank(key: string): number {
  const index = GROUP_ORDER.indexOf(key);
  return index === -1 ? GROUP_ORDER.length : index;
}

function groupExtractions(
  extractions: readonly WireExtraction[],
): [string, WireExtraction[]][] {
  const groups = new Map<string, WireExtraction[]>();
  for (const extraction of extractions) {
    const list = groups.get(extraction.group_key);
    if (list === undefined) groups.set(extraction.group_key, [extraction]);
    else list.push(extraction);
  }
  // sort 是稳定排序：同组内保持接口给出的顺序
  return [...groups.entries()].sort(([a], [b]) => groupRank(a) - groupRank(b));
}

interface Props {
  extractions: readonly WireExtraction[];
  index: EvidenceIndex;
  onLocate: (target: EvidenceTarget) => void;
}

export function ResultPanel({ extractions, index, onLocate }: Props) {
  const groups = groupExtractions(extractions);
  const pending = extractions.filter(
    (item) => item.status === "need_review" || item.status === "conflict",
  ).length;
  const notFound = extractions.filter((item) => item.status === "not_found").length;

  return (
    <aside className="flex w-[420px] shrink-0 flex-col border-l border-slate-200 bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">解析结果</h3>
        <p className="mt-1 text-xs tabular-nums text-slate-500">
          共 {extractions.length} 项 · 待复核 {pending} 项 · 未找到 {notFound} 项
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {groups.map(([key, items]) => (
          <section key={key} className="mb-6 last:mb-0">
            <h4 className="mb-2 text-xs font-semibold tracking-wide text-slate-500">
              {GROUP_LABELS[key] ?? key}
            </h4>
            <div className="flex flex-col gap-2">
              {items.map((item) => (
                <ResultCard
                  key={item.id}
                  extraction={item}
                  targets={index.byExtraction.get(item.id) ?? NO_TARGETS}
                  onLocate={onLocate}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </aside>
  );
}