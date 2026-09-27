"use client";

/**
 * 单条字段结果卡：值 + 置信度 + 状态徽标 + 证据数 + 定位（见 docs/设计/06 第 2 节）。
 *
 * 本切片只做「读 + 定位」：复核动作（确认/修正/补充/驳回）、尝试链、重跑入口都依赖后端接口，
 * 留待后续切片（见 06 第 9 节）。但**未找到的字段照常列出、不隐藏**——隐藏会让用户以为系统漏了，
 * 而这恰恰是最需要人工处理的字段（见 06 第 9.2 节）。
 *
 * 多条证据时反复点「定位」按证据循环：只画第一条会让用户以为其余证据不存在。
 */

import { useState } from "react";

import type { EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { ExtractionStatus, WireExtraction } from "@/types/workbench";

import { cycleEvidence } from "@/hooks/useEvidenceIndex";

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
  const [cursor, setCursor] = useState(0);
  const meta = STATUS_META[extraction.status];
  const isNotFound = extraction.status === "not_found";
  const nextNo = targets.length === 0 ? 0 : (cursor % targets.length) + 1;

  const handleLocate = () => {
    const target = cycleEvidence(targets, cursor);
    if (target === null) return;
    onLocate(target);
    setCursor((value) => value + 1);
  };

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
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

      <footer className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
        {!isNotFound && (
          <span className="tabular-nums">置信度 {(extraction.confidence * 100).toFixed(0)}%</span>
        )}
        <span className="tabular-nums">证据 {targets.length} 处</span>
        <button
          type="button"
          onClick={handleLocate}
          disabled={targets.length === 0}
          className="ml-auto rounded border border-sky-300 bg-sky-50 px-2 py-1 text-xs text-sky-700 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {targets.length > 1 ? `定位（证据 ${nextNo}/${targets.length}）` : "定位原文"}
        </button>
      </footer>

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