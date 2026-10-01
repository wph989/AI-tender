"use client";

/**
 * 结果面板：分组标签页 + 当前分组的字段卡片（见 docs/设计/06 第 2.1 节）。
 *
 * 为什么用标签而不是一列到底：一个项目 500+ 条结果，全部铺开时「找某一组字段」要靠滚动碰运气；
 * 标签一次只呈现一组，滚动长度可控，也不会出现「翻了二十屏才想起还有个风险条款组」。
 *
 * 默认选第一个分组（业务顺序里最靠前的），切标签时滚动位置重置——标签换了还停在半截
 * 会让用户以为这组内容就在下面。
 *
 * 批量确认只覆盖「自动抽取」：这一档本来就是没人看过的，一键确认是它的正常出口；
 * 待复核/冲突/未找到仍然必须逐条处理（见 lib/results/grouping.ts 的选择函数）。
 *
 * 两档视图（见 06 第 11 节的复核模式）：两档共用同一份数据，只换顺序与展开状态，
 * 不做过滤——复核到一半切回「全部结果」要能立刻找回上下文，而不是发现少了几条。
 */

import type { KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { DATA_CLASS, EYEBROW_CLASS, INPUT_CLASS, RESULT_PANEL_WIDTH } from "@/components/ui";
import type { ReviewInput } from "@/lib/api/client";
import { buildResultTabs, selectBatchConfirmable } from "@/lib/results/grouping";
import { needsActionCount, orderForReview } from "@/lib/results/reviewQueue";
import { rerunMode, type RerunButtonMode } from "@/lib/results/rerun";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceIndex, EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireAttempt, WireConflict, WireExtraction } from "@/types/workbench";

import { ConflictsPanel } from "./ConflictsPanel";
import { ResultCard } from "./ResultCard";
import { ResultGroupTabs } from "./ResultGroupTabs";

const NO_TARGETS: readonly EvidenceTarget[] = [];
const NO_CONFLICTS: ReadonlyMap<string, WireConflict> = new Map<string, WireConflict>();

interface Props {
  extractions: readonly WireExtraction[];
  index: EvidenceIndex;
  /** 项目级动作（冲突裁定）用它定位；静态样本为 null。 */
  projectId: number | null;
  /** 服务端下发的重跑按钮口径（09 第 8 节）；没有统计的字段回落 show。 */
  rerunModes: Record<string, RerunButtonMode>;
  busyExtractionId: number | null;
  /** 复核队列：冲突/待复核排最前，冲突项就地展开两侧取值（见 06 第 11 节）。 */
  reviewOnly: boolean;
  onReviewModeChange: (next: boolean) => void;
  /** 字段 key → 该项目该字段的未裁定冲突。由工作台统一取一次，避免每张卡各查一遍。 */
  conflictsByField?: ReadonlyMap<string, WireConflict>;
  onLocate: (target: EvidenceTarget) => void;
  onReview: (extraction: WireExtraction, input: ReviewInput) => Promise<boolean>;
  onRerun: (extraction: WireExtraction, hint: string | null) => Promise<boolean>;
  onResolveConflict?: (conflictId: number, resolvedId: number) => Promise<void>;
  onBatchConfirm: (extractions: readonly WireExtraction[]) => Promise<void>;
  onRefresh: () => Promise<void>;
  onNotice: (message: string | null) => void;
  onLoadAttempts: (extractionId: number) => Promise<WireAttempt[]>;
}

function ModeButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={
        "rounded-[2px] border px-2 py-1 text-[13px] transition-colors " +
        (active
          ? "border-slate-900 bg-slate-900 font-medium text-white"
          : "border-slate-300 bg-white text-slate-600 hover:border-slate-500 hover:bg-slate-50")
      }
    >
      {label}
    </button>
  );
}

export function ResultPanel({
  extractions,
  index,
  projectId,
  rerunModes,
  busyExtractionId,
  reviewOnly,
  onReviewModeChange,
  conflictsByField = NO_CONFLICTS,
  onLocate,
  onReview,
  onRerun,
  onResolveConflict,
  onBatchConfirm,
  onRefresh,
  onNotice,
  onLoadAttempts,
}: Props) {
  const tabs = useMemo(() => buildResultTabs(extractions), [extractions]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  // 数据重载后原分组可能消失：回退到第一个分组，而不是留下一个空白面板
  const active = tabs.find((tab) => tab.key === activeKey) ?? tabs[0];

  // 键盘游标：j/k 在「当前显示顺序」里移动，Enter 处理。它是「正在读的那一条」，
  // 与 activeEvidence（原文高亮）不同——但两者互为镜像，见下面的反向联动。
  const [cursorId, setCursorId] = useState<number | null>(null);
  const [rerunSignal, setRerunSignal] = useState<{ id: number; token: number }>({
    id: 0,
    token: 0,
  });
  const [keyword, setKeyword] = useState("");
  const searchRef = useRef<HTMLInputElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const lastLocatedRef = useRef<number | null>(null);

  const locatedId = useViewerStore((state) => state.activeEvidence?.extractionId ?? null);

  // 原文角标 → 结果卡的反向联动。只在「定位目标真的换了」时执行：
  // 每次数据刷新都重跑会把用户手动切过去的分组又拽回来。
  useEffect(() => {
    if (locatedId === null || locatedId === lastLocatedRef.current) return;
    lastLocatedRef.current = locatedId;
    // 章节树跳转也写 activeEvidence，但用的是哨兵 id（-1）；只接管真属于本版本的结果
    const owner = tabs.find((tab) => tab.items.some((item) => item.id === locatedId));
    if (owner === undefined) return;
    setCursorId(locatedId);
    setActiveKey(owner.key);
  }, [locatedId, tabs]);

  const visibleItems = useMemo(() => {
    if (active === undefined) return [];
    const ordered = reviewOnly ? orderForReview(active.items) : active.items;
    const needle = keyword.trim().toLowerCase();
    if (needle === "") return ordered;
    return ordered.filter((item) => {
      const label = item.field_label ?? item.field_key;
      return (
        label.toLowerCase().includes(needle) ||
        item.field_key.toLowerCase().includes(needle) ||
        item.value_text.toLowerCase().includes(needle)
      );
    });
  }, [active, keyword, reviewOnly]);

  const pending = needsActionCount(extractions);
  const notFound = extractions.filter((item) => item.status === "not_found").length;
  const batchable = active === undefined ? [] : selectBatchConfirmable(active.items);

  const moveCursor = (delta: number) => {
    if (visibleItems.length === 0) return;
    const current = visibleItems.findIndex((item) => item.id === cursorId);
    // 光标还没落下来时：按 j 从第一条开始，按 k 从最后一条开始。
    const base = current === -1 ? (delta > 0 ? -1 : visibleItems.length) : current;
    const next = visibleItems[Math.min(Math.max(base + delta, 0), visibleItems.length - 1)];
    if (next === undefined) return;
    setCursorId(next.id);
    // 焦点收回面板：光标移动后 j/k 必须继续在当前面板生效，而不是留在刚点过的按钮上
    panelRef.current?.focus({ preventScroll: true });
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const target = event.target as HTMLElement;
    const editable =
      target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;

    if (editable) {
      // 在输入框里 Esc 只做「退出输入」，不要把整个高亮清掉
      if (event.key === "Escape") (target as HTMLInputElement).blur();
      return;
    }

    if (event.key === "/") {
      event.preventDefault();
      searchRef.current?.focus();
      return;
    }
    if (event.key === "j") {
      event.preventDefault();
      moveCursor(1);
      return;
    }
    if (event.key === "k") {
      event.preventDefault();
      moveCursor(-1);
      return;
    }
    if (event.key === "Escape") {
      setCursorId(null);
      return;
    }
    if (event.key !== "Enter") return;

    // 焦点在按钮/链接上时 Enter 属于那个控件：不抢，否则一次回车会既点了按钮又确认了结果
    if (target.tagName === "BUTTON" || target.tagName === "A") return;
    const item = visibleItems.find((entry) => entry.id === cursorId);
    if (item === undefined) return;
    event.preventDefault();
    if (event.shiftKey) {
      setRerunSignal((prev) => ({ id: item.id, token: prev.token + 1 }));
      return;
    }
    void onReview(item, { attempt_id: item.id, action: "confirm", review_mode: "item" });
  };

  return (
    <aside
      ref={panelRef}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      className={RESULT_PANEL_WIDTH + " flex shrink-0 flex-col border-l border-slate-200 focus:outline-none"}
    >
      <div className="border-b border-slate-200 bg-white px-4 pt-3.5 pb-3">
        <div className="flex items-baseline justify-between gap-3">
          <p className={EYEBROW_CLASS}>{reviewOnly ? "复核队列" : "解析结果"}</p>
          <span className={DATA_CLASS + " text-[13px] text-slate-400"}>
            共 {extractions.length} 项
          </span>
        </div>

        <div className="mt-2 flex items-center gap-1" role="tablist" aria-label="结果视图">
          <ModeButton
            active={reviewOnly}
            label="复核队列"
            onClick={() => onReviewModeChange(true)}
          />
          <ModeButton
            active={!reviewOnly}
            label="全部结果"
            onClick={() => onReviewModeChange(false)}
          />
        </div>

        <p className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px] text-slate-500">
          <span>
            待复核{" "}
            <span
              className={
                DATA_CLASS +
                (pending > 0 ? " mark-ink ml-0.5 px-1 text-slate-900" : " ml-0.5 text-slate-400")
              }
            >
              {pending}
            </span>
          </span>
          <span aria-hidden className="text-slate-300">
            ·
          </span>
          <span>
            未找到{" "}
            <span
              className={
                DATA_CLASS + " ml-0.5 " + (notFound > 0 ? "text-slate-700" : "text-slate-400")
              }
            >
              {notFound}
            </span>
          </span>
          <span className="ml-auto text-[11px] text-slate-400">
            j/k 移动 · Enter 确认 · Shift+Enter 带提示重跑
          </span>
        </p>

        <input
          ref={searchRef}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="筛选字段名或值（/ 聚焦）"
          aria-label="筛选字段"
          className={INPUT_CLASS + " mt-2 w-full py-1"}
        />

        <ConflictsPanel projectId={projectId} onNotice={onNotice} onResolved={onRefresh} />
      </div>

      {active === undefined ? (
        <div className="flex flex-1 items-center justify-center px-4 text-[14px] text-slate-500">
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
            className="min-h-0 flex-1 overflow-y-auto bg-slate-50 px-4 py-4"
          >
            {!reviewOnly && batchable.length > 0 && (
              <div className="relative mb-3 flex items-center gap-2 border border-emerald-200 bg-emerald-50 py-1.5 pr-2 pl-3 text-[13px] text-emerald-800">
                <span aria-hidden className="absolute inset-y-0 left-0 w-[4px] bg-emerald-500" />
                <span className="flex-1">{batchable.length} 项自动抽取无需逐条查看</span>
                <button
                  type="button"
                  onClick={() => void onBatchConfirm(batchable)}
                  disabled={busyExtractionId !== null}
                  className="border border-emerald-300 bg-white px-2 py-0.5 hover:bg-emerald-100 disabled:opacity-40"
                >
                  批量确认
                </button>
              </div>
            )}

            {visibleItems.length === 0 ? (
              <p className="px-1 py-6 text-center text-[13px] text-slate-400">
                没有匹配「{keyword.trim()}」的字段
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {visibleItems.map((item) => (
                  <ResultCard
                    key={item.id}
                    extraction={item}
                    targets={index.byExtraction.get(item.id) ?? NO_TARGETS}
                    rerunButton={rerunMode(rerunModes, item.field_key)}
                    busy={busyExtractionId === item.id}
                    highlighted={item.id === cursorId}
                    forceOpen={reviewOnly && item.status === "conflict"}
                    conflict={conflictsByField.get(item.field_key) ?? null}
                    onResolveConflict={onResolveConflict}
                    openRerunToken={rerunSignal.id === item.id ? rerunSignal.token : 0}
                    onLocate={onLocate}
                    onReview={(input) => onReview(item, input)}
                    onRerun={(hint) => onRerun(item, hint)}
                    onLoadAttempts={onLoadAttempts}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  );
}