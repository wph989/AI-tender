"use client";

/**
 * 单条字段结果卡：值、证据定位和复核操作。
 *
 * 人工修正必须把锚点一起提交：编辑器会预填当前证据，也允许在反向标注模式下
 * 手动输入当前 run 的锚点，后端仍会再次校验锚点属于该版本。
 */

import { useState } from "react";

import type { ReviewEvidenceInput, ReviewInput } from "@/lib/api/client";
import { statusBadgeClass, statusLabel, triggerLabel } from "@/lib/results/labels";
import type { RerunButtonMode } from "@/lib/results/rerun";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireAttempt, WireExtraction } from "@/types/workbench";

import { AttemptHistory } from "./AttemptHistory";
import { EvidenceList } from "./EvidenceList";

interface Props {
  extraction: WireExtraction;
  targets: readonly EvidenceTarget[];
  /** 服务端下发的重跑按钮口径（09 第 8 节）；hide 时只保留不占主位的入口。 */
  rerunButton?: RerunButtonMode;
  busy: boolean;
  onLocate: (target: EvidenceTarget) => void;
  onReview: (input: ReviewInput) => Promise<boolean>;
  onRerun: (hint: string | null) => Promise<boolean>;
  onLoadAttempts: (extractionId: number) => Promise<WireAttempt[]>;
}

type EditMode = "correct" | "supplement" | null;

export function ResultCard({
  extraction,
  targets,
  rerunButton = "show",
  busy,
  onLocate,
  onReview,
  onRerun,
  onLoadAttempts,
}: Props) {
  const badgeClass = statusBadgeClass(extraction.status);
  const label = statusLabel(extraction.status);
  const isNotFound = extraction.status === "not_found";
  const [editMode, setEditMode] = useState<EditMode>(null);
  const [draftValue, setDraftValue] = useState(extraction.value_text);
  const [draftAnchor, setDraftAnchor] = useState(targets[0]?.anchor ?? "");
  const [draftQuote, setDraftQuote] = useState(targets[0]?.quote ?? "");
  const [rerunOpen, setRerunOpen] = useState(false);
  const [rerunHint, setRerunHint] = useState("");
  const [attemptsOpen, setAttemptsOpen] = useState(false);
  const [attempts, setAttempts] = useState<WireAttempt[] | null>(null);
  const [attemptsLoading, setAttemptsLoading] = useState(false);
  const [attemptsError, setAttemptsError] = useState<string | null>(null);
  const activeAnchor = useViewerStore((state) =>
    state.activeEvidence !== null && state.activeEvidence.extractionId === extraction.id
      ? state.activeEvidence.anchor
      : null,
  );
  const onlyTarget = targets.length === 1 ? targets[0] : undefined;

  const beginEdit = (mode: EditMode) => {
    setEditMode(mode);
    setDraftValue(isNotFound ? "" : extraction.value_text);
    setDraftAnchor(targets[0]?.anchor ?? "");
    setDraftQuote(targets[0]?.quote ?? "");
  };

  const submitEdit = async () => {
    const value = draftValue.trim();
    const anchor = draftAnchor.trim();
    if (!value || !anchor) return;
    const evidence: ReviewEvidenceInput[] = [
      { anchor, quote: draftQuote.trim() || undefined },
    ];
    const succeeded = await onReview({
      attempt_id: extraction.id,
      action: editMode === "supplement" ? "supplement" : "correct",
      review_mode: "item",
      new_value: value,
      evidence,
    });
    if (succeeded) setEditMode(null);
  };

  const submitConfirm = async () => {
    await onReview({
      attempt_id: extraction.id,
      action: "confirm",
      review_mode: "item",
    });
  };

  const submitReject = async () => {
    await onReview({
      attempt_id: extraction.id,
      action: "reject",
      review_mode: "item",
      comment: "用户在结果面板驳回",
    });
  };

  const submitRerun = async () => {
    const succeeded = await onRerun(rerunHint.trim() || null);
    if (succeeded) {
      setRerunOpen(false);
      setRerunHint("");
    }
  };

  const toggleAttempts = () => {
    if (attemptsOpen) {
      setAttemptsOpen(false);
      return;
    }
    setAttemptsOpen(true);
    if (attempts !== null || attemptsLoading) return;
    setAttemptsLoading(true);
    setAttemptsError(null);
    void onLoadAttempts(extraction.id)
      .then((items) => setAttempts(items))
      .catch((error: unknown) => {
        setAttemptsError(error instanceof Error ? error.message : "尝试链加载失败");
      })
      .finally(() => setAttemptsLoading(false));
  };

  return (
    <article
      data-extraction-id={extraction.id}
      className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
    >
      <header className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-medium text-slate-900">
          {extraction.field_label ?? extraction.field_key}
        </h4>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-xs ${badgeClass}`}>
          {label}
        </span>
      </header>

      {isNotFound ? (
        <p className="mt-2 text-sm text-slate-500">未在本文档中找到</p>
      ) : (
        <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-900">
          {extraction.value_text}
        </p>
      )}

      {(extraction.machine_attempt_no !== null && extraction.machine_attempt_no !== undefined) ||
        extraction.trigger === "manual_edit" ? (
        <p className="mt-2 text-xs text-slate-400">
          {extraction.machine_attempt_no === null || extraction.machine_attempt_no === undefined
            ? "人工"
            : "第 " + extraction.machine_attempt_no + " 次机器尝试"}{" "}
          · {triggerLabel(extraction.trigger)}
        </p>
      ) : null}

      {!isNotFound && (
        <footer className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="tabular-nums">置信度 {(extraction.confidence * 100).toFixed(0)}%</span>
          {onlyTarget !== undefined && (
            <button
              type="button"
              onClick={() => onLocate(onlyTarget)}
              className={buttonClass}
              disabled={busy}
            >
              定位第 {onlyTarget.pageNo} 页
            </button>
          )}
        </footer>
      )}

      {targets.length > 1 && (
        <EvidenceList targets={targets} activeAnchor={activeAnchor} onLocate={onLocate} />
      )}

      <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
        {isNotFound ? (
          <>
            <button type="button" className={buttonClass} disabled={busy} onClick={submitConfirm}>
              确认没有
            </button>
            <button type="button" className={buttonClass} disabled={busy} onClick={() => beginEdit("supplement")}>
              人工补充
            </button>
          </>
        ) : (
          <>
            <button type="button" className={buttonClass} disabled={busy} onClick={submitConfirm}>
              确认
            </button>
            <button type="button" className={buttonClass} disabled={busy} onClick={() => beginEdit("correct")}>
              修正
            </button>
            {rerunButton !== "hide" && (
              <button
                type="button"
                className={buttonClass}
                disabled={busy}
                onClick={() => setRerunOpen((open) => !open)}
              >
                重跑
              </button>
            )}
            <button type="button" className={buttonClass} disabled={busy} onClick={submitReject}>
              驳回
            </button>
          </>
        )}
      </div>

      {!isNotFound && rerunButton === "show_hint" && (
        <p className="mt-2 text-xs text-emerald-700">重跑一次通常能修好</p>
      )}

      {rerunButton === "hide" && !isNotFound && !rerunOpen && (
        <button
          type="button"
          className="mt-2 text-xs text-slate-400 hover:text-slate-600 hover:underline"
          onClick={() => setRerunOpen(true)}
          disabled={busy}
        >
          该字段重跑通常无用，仍要重跑
        </button>
      )}

      <button
        type="button"
        className="mt-2 text-xs text-slate-500 hover:text-slate-700 hover:underline"
        onClick={toggleAttempts}
        disabled={busy}
      >
        {attemptsOpen ? "收起尝试链" : "查看尝试链"}
      </button>

      {attemptsOpen && (
        <AttemptHistory
          attempts={attempts ?? []}
          loading={attemptsLoading}
          error={attemptsError}
          onLocate={onLocate}
        />
      )}

      {rerunOpen && (
        <div className="mt-2 flex flex-col gap-2 rounded border border-slate-200 bg-slate-50 p-2">
          <input
            value={rerunHint}
            onChange={(event) => setRerunHint(event.target.value)}
            placeholder="可选：提示模型重点查看的章节"
            className={inputClass}
          />
          <button type="button" className={primaryClass} disabled={busy} onClick={submitRerun}>
            提交重跑
          </button>
        </div>
      )}

      {editMode !== null && (
        <div className="mt-2 flex flex-col gap-2 rounded border border-sky-200 bg-sky-50 p-2">
          <input
            value={draftValue}
            onChange={(event) => setDraftValue(event.target.value)}
            placeholder="填写修正后的值"
            className={inputClass}
          />
          <input
            value={draftAnchor}
            onChange={(event) => setDraftAnchor(event.target.value)}
            placeholder="原文锚点，例如 p12b5"
            className={inputClass}
          />
          <textarea
            value={draftQuote}
            onChange={(event) => setDraftQuote(event.target.value)}
            placeholder="可选：锚点中的原文片段"
            rows={2}
            className={inputClass}
          />
          <div className="flex gap-2">
            <button
              type="button"
              className={primaryClass}
              disabled={busy || !draftValue.trim() || !draftAnchor.trim()}
              onClick={() => void submitEdit()}
            >
              提交{editMode === "supplement" ? "补充" : "修正"}
            </button>
            <button type="button" className={buttonClass} disabled={busy} onClick={() => setEditMode(null)}>
              取消
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

const buttonClass =
  "rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";
const primaryClass =
  "rounded border border-sky-400 bg-sky-600 px-2 py-1 text-xs text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50";
const inputClass =
  "w-full rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 focus:border-sky-500 focus:outline-none";
