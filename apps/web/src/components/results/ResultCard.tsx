"use client";

/**
 * 单条字段结果卡：值 + 置信度 + 状态徽标 + 证据（见 docs/设计/06 第 2 / 2.1 节）。
 *
 * 本切片只做「读 + 定位」：复核动作（确认/修正/补充/驳回）、尝试链、重跑入口都依赖后端接口，
 * 留待后续切片（见 06 第 9 节）。但**未找到的字段照常列出、不隐藏**——隐藏会让用户以为系统漏了，
 * 而这恰恰是最需要人工处理的字段（见 06 第 9.2 节）。
 *
 * 证据的呈现分两档（见 06 第 2.1 节）：
 *  - 1 处：行内一个「定位原文」按钮，卡片保持紧凑；
 *  - 多 处：展开成证据列表（页码 + 引文逐条点击定位）——一个结果可能从多处溯源而来，
 *    必须先让用户看到"有哪几处、在哪一页"，才谈得上选择。
 */

import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { ExtractionStatus, WireExtraction } from "@/types/workbench";

import { EvidenceList } from "./EvidenceList";

/** 与库内枚举一一对应（见 docs/设计/03 表结构）。文案固定在这里，不允许各处自造。 */
const STATUS_META: Record<ExtractionStatus, { label: string; className: string }> = {
  auto: { label: "自动抽取", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  need_review: { label: "待复核", className: "border-amber-200 bg-amber-50 text-amber-700" },
  verified: { label: "已确认", className: "border-sky-200 bg-sky-50 text-sky-700" },
  rejected: { label: "已驳回", className: "border-slate-200 bg-slate-100 text-slate-500" },
  conflict: { label: "存在冲突", className: "border-rose-200 bg-rose-50 text-rose-700" },
  not_found: { label: "未找到", className: "border-slate-300 bg-slate-100 text-slate-600" },
};

interface Props {
  extraction: WireExtraction;
  targets: readonly EvidenceTarget[];
  onLocate: (target: EvidenceTarget) => void;
}

export function ResultCard({ extraction, targets, onLocate }: Props) {
  const meta = STATUS_META[extraction.status];
  const isNotFound = extraction.status === "not_found";
  // 只订阅"本卡是否高亮"这一个布尔值派生量：500 张卡片不会因为别的卡片定位而整体重渲染
  const activeAnchor = useViewerStore((state) =>
    state.activeEvidence !== null && state.activeEvidence.extractionId === extraction.id
      ? state.activeEvidence.anchor
      : null,
  );
  const onlyTarget = targets.length === 1 ? targets[0] : undefined;

  return (
    <article data-extraction-id={extraction.id} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <header className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-medium text-slate-900">
          {extraction.field_label ?? extraction.field_key}
        </h4>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-xs ${meta.className}`}>
          {meta.label}
        </span>
      </header>

      {isNotFound ? (
        <p className="mt-2 text-sm text-slate-500">未在本文档中找到</p>
      ) : (
        <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-900">
          {extraction.value_text}
        </p>
      )}

      {!isNotFound && (
        <footer className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <span className="tabular-nums">置信度 {(extraction.confidence * 100).toFixed(0)}%</span>
          {onlyTarget !== undefined && (
            <button
              type="button"
              onClick={() => onLocate(onlyTarget)}
              className="ml-auto rounded border border-sky-300 bg-sky-50 px-2 py-1 text-xs text-sky-700 hover:bg-sky-100"
            >
              定位原文 · 第 {onlyTarget.pageNo} 页
            </button>
          )}
        </footer>
      )}

      {targets.length > 1 && (
        <EvidenceList targets={targets} activeAnchor={activeAnchor} onLocate={onLocate} />
      )}

      {isNotFound && (
        <div className="mt-3 flex items-center gap-2 border-t border-dashed border-slate-200 pt-3 text-xs">
          <button type="button" disabled title="接口落地后启用（本切片只做定位闭环）" className={secondaryAction}>
            确认没有
          </button>
          <button type="button" disabled title="接口落地后启用（本切片只做定位闭环）" className={secondaryAction}>
            人工补充
          </button>
          <span className="text-slate-400">接口落地后启用</span>
        </div>
      )}
    </article>
  );
}

const secondaryAction =
  "rounded border border-slate-300 px-2 py-1 text-slate-600 disabled:cursor-not-allowed disabled:opacity-50";