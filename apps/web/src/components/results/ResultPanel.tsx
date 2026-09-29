"use client";

/**
 * 结果面板：分组标签页 + 当前分组的字段卡片（见 docs/设计/06 第 2.1 节）。
 *
 * 为什么用标签而不是一列到底：一个项目 500+ 条结果，全部铺开时"找某一组字段"要靠滚动碰运气；
 * 标签一次只呈现一组，滚动长度可控，也不会出现"翻了二十屏才想起还有个风险条款组"。
 *
 * 默认选第一个分组（业务顺序里最靠前的），切标签时滚动位置重置——标签换了还停在半截
 * 会让用户以为这组内容就在下面。
 *
 * 批量确认只覆盖「自动抽取」：这一档本来就是没人看过的，一键确认是它的正常出口；
 * 待复核/冲突/未找到仍然必须逐条处理（见 lib/results/grouping.ts 的选择函数）。
 */

import { useMemo, useState } from "react";

import type { ReviewInput } from "@/lib/api/client";
import { buildResultTabs, selectBatchConfirmable } from "@/lib/results/grouping";
import { rerunMode, type RerunButtonMode } from "@/lib/results/rerun";
import type { EvidenceIndex, EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireAttempt, WireExtraction } from "@/types/workbench";

import { ConflictsPanel } from "./ConflictsPanel";
import { ResultCard } from "./ResultCard";
import { ResultGroupTabs } from "./ResultGroupTabs";

const NO_TARGETS: readonly EvidenceTarget[] = [];

interface Props {
  extractions: readonly WireExtraction[];
  index: EvidenceIndex;
  /** 项目级动作（冲突裁定）用它定位；静态样本为 null。 */
  projectId: number | null;
  /** 服务端下发的重跑按钮口径（09 第 8 节）；没有统计的字段回落 show。 */
  rerunModes: Record<string, RerunButtonMode>;
  busyExtractionId: number | null;
  onLocate: (target: EvidenceTarget) => void;
  onReview: (extraction: WireExtraction, input: ReviewInput) => Promise<boolean>;
  onRerun: (extraction: WireExtraction, hint: string | null) => Promise<boolean>;
  onBatchConfirm: (extractions: readonly WireExtraction[]) => Promise<void>;
  onRefresh: () => Promise<void>;
  onNotice: (message: string | null) => void;
  onLoadAttempts: (extractionId: number) => Promise<WireAttempt[]>;
}

export function ResultPanel({
  extractions,
  index,
  projectId,
  rerunModes,
  busyExtractionId,
  onLocate,
  onReview,
  onRerun,
  onBatchConfirm,
  onRefresh,
  onNotice,
  onLoadAttempts,
}: Props) {
  const tabs = useMemo(() => buildResultTabs(extractions), [extractions]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  // 数据重载后原分组可能消失：回退到第一个分组，而不是留下一个空白面板
  const active = tabs.find((tab) => tab.key === activeKey) ?? tabs[0];

  const pending = extractions.filter(
    (item) => item.status === "need_review" || item.status === "conflict",
  ).length;
  const notFound = extractions.filter((item) => item.status === "not_found").length;
  const batchable = active === undefined ? [] : selectBatchConfirmable(active.items);

  return (
    <aside className="flex w-[420px] shrink-0 flex-col border-l border-slate-200 bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">解析结果</h3>
        <p className="mt-1 text-xs tabular-nums text-slate-500">
          共 {extractions.length} 项 · 待复核 {pending} 项 · 未找到 {notFound} 项
        </p>
        <ConflictsPanel projectId={projectId} onNotice={onNotice} onResolved={onRefresh} />
      </div>

      {active === undefined ? (
        <div className="flex flex-1 items-center justify-center px-4 text-sm text-slate-500">
          暂无解析结果
        </div>
      ) : (
        <>
          <ResultGroupTabs tabs={tabs} activeKey={active.key} onSelect={setActiveKey} />
          <div
            key={active.key}
            role="tabpanel"
            id={`result-tabpanel-${active.key}`}
            aria-labelledby={`result-tab-${active.key}`}
            className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
          >
            {batchable.length > 0 && (
              <div className="mb-2 flex items-center justify-between rounded border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs text-emerald-800">
                <span>{batchable.length} 项自动抽取无需逐条查看</span>
                <button
                  type="button"
                  onClick={() => void onBatchConfirm(batchable)}
                  disabled={busyExtractionId !== null}
                  className="rounded border border-emerald-300 px-2 py-0.5 hover:bg-emerald-100 disabled:opacity-40"
                >
                  批量确认
                </button>
              </div>
            )}
            <div className="flex flex-col gap-2">
              {active.items.map((item) => (
                <ResultCard
                  key={item.id}
                  extraction={item}
                  targets={index.byExtraction.get(item.id) ?? NO_TARGETS}
                  rerunButton={rerunMode(rerunModes, item.field_key)}
                  busy={busyExtractionId === item.id}
                  onLocate={onLocate}
                  onReview={(input) => onReview(item, input)}
                  onRerun={(hint) => onRerun(item, hint)}
                  onLoadAttempts={onLoadAttempts}
                />
              ))}
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
