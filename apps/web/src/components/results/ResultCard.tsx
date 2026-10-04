"use client";

/**
 * 单条字段结果卡：值、证据定位和复核操作。
 *
 * 版式按「读的顺序」排：字段名 → 值 → 出处 → 动作。
 * 结果用无衬线正文保证长条款可读，原文入口使用同色连接框，便于识别溯源动作。
 *
 * 人工修正必须把锚点一起提交：编辑器会预填当前证据，也允许在反向标注模式下
 * 手动输入当前 run 的锚点，后端仍会再次校验锚点属于该版本。
 */

import { useEffect, useRef, useState } from "react";

import {
  BUTTON_CLASS,
  DATA_CLASS,
  DANGER_GHOST_BUTTON_CLASS,
  GHOST_BUTTON_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
} from "@/components/ui";
import type { ReviewEvidenceInput, ReviewInput } from "@/lib/api/client";
import {
  statusDotClass,
  statusLabel,
  statusTextClass,
} from "@/lib/results/labels";
import type { RerunButtonMode } from "@/lib/results/rerun";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireAttempt, WireConflict, WireExtraction } from "@/types/workbench";

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
  /** 键盘 j/k 或原文角标选中的那一张：加一圈紫色描边并滚进视野。 */
  highlighted?: boolean;
  /** 复核模式下强制展开证据：排队处理时不该还要逐条点开才看得到出处。 */
  forceOpen?: boolean;
  /** 与这条结果同字段的未裁定冲突；有值时卡片内直接摆出两侧取值待裁决。 */
  conflict?: WireConflict | null;
  onResolveConflict?: (conflictId: number, resolvedId: number) => Promise<void>;
  /** 自增令牌：变化时展开「带提示重跑」并聚焦输入框（结果面板的 Shift+Enter）。 */
  openRerunToken?: number;
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
  highlighted = false,
  forceOpen = false,
  conflict = null,
  onResolveConflict,
  openRerunToken = 0,
}: Props) {
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
  const rootRef = useRef<HTMLElement | null>(null);
  const rerunInputRef = useRef<HTMLInputElement | null>(null);
  const [conflictBusy, setConflictBusy] = useState(false);

  // Shift+Enter：展开重跑面板并把光标送进提示输入框，用户接着打字即可。
  // 下一帧再聚焦：输入框是这一帧才挂上去的，同帧 focus 会落空。
  useEffect(() => {
    if (openRerunToken === 0) return;
    setRerunOpen(true);
    const frame = requestAnimationFrame(() => rerunInputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [openRerunToken]);

  // 键盘/角标选中时把卡片带回视野。用 nearest 而不是 center：
  // 连续按 j/k 时 center 会让整屏不停上下翻，读不出一条结果。
  useEffect(() => {
    if (!highlighted) return;
    rootRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [highlighted]);

  const decideConflict = async (resolvedId: number) => {
    if (conflict === null || onResolveConflict === undefined) return;
    setConflictBusy(true);
    try {
      await onResolveConflict(conflict.id, resolvedId);
    } finally {
      setConflictBusy(false);
    }
  };

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
    const evidence: ReviewEvidenceInput[] = [{ anchor, quote: draftQuote.trim() || undefined }];
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

  const attemptNote =
    extraction.machine_attempt_no === null || extraction.machine_attempt_no === undefined
      ? extraction.trigger === "manual_edit"
        ? "人工"
        : null
      : "第 " + extraction.machine_attempt_no + " 次机器尝试";

  return (
    <article
      ref={rootRef}
      data-extraction-id={extraction.id}
      className={
        "result-card " +
        (highlighted
          ? "is-highlighted"
          : activeAnchor !== null
            ? "is-located"
            : "border-slate-200")
      }
    >
      <div className="px-3.5 pt-2.5 pb-2">
        <header className="flex items-start justify-between gap-2">
          <h4 className="font-display font-semibold text-[15px] leading-[22px] text-slate-900">
            {extraction.field_label ?? extraction.field_key}
          </h4>
          <span className="flex shrink-0 items-center gap-1.5 text-[13px]">
            <span
              aria-hidden
              className={"h-1.5 w-1.5 rounded-full " + statusDotClass(extraction.status)}
            />
            <span className={statusTextClass(extraction.status)}>{label}</span>
          </span>
        </header>

        {isNotFound ? (
          <p className="mt-2 text-[14px] text-slate-400">本文档中未提及</p>
        ) : (
          <p
            className={
              DATA_CLASS +
              " mt-2 result-value break-words whitespace-pre-wrap text-slate-900"
            }
          >
            {extraction.value_text}
          </p>
        )}

        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-slate-400">
          {!isNotFound && (
            <span className={DATA_CLASS}>置信度 {(extraction.confidence * 100).toFixed(0)}%</span>
          )}
          {attemptNote !== null && (
            <>
              {!isNotFound && <span aria-hidden>·</span>}
              <span>{attemptNote}</span>
            </>
          )}
          <button
            type="button"
            className="ml-auto text-[13px] text-slate-500 hover:text-slate-900 hover:underline"
            onClick={toggleAttempts}
            disabled={busy}
          >
            {attemptsOpen ? "收起尝试链" : "查看尝试链"}
          </button>
        </p>

        {onlyTarget !== undefined && !forceOpen && (
          <button
            type="button"
            onClick={() => onLocate(onlyTarget)}
            disabled={busy}
            className={
              "mt-3 flex w-full items-center justify-between gap-2 rounded-lg border border-sky-100 bg-sky-50 px-3 py-2 " +
              "text-[12px] text-sky-700 hover:border-sky-300 hover:bg-sky-100 disabled:opacity-40"
            }
          >
            <span className={DATA_CLASS}>第 {onlyTarget.pageNo} 页</span>
            <span aria-hidden>·</span>
            <span>定位原文</span>
          </button>
        )}
      </div>

      {(targets.length > 1 || (forceOpen && targets.length > 0)) && (
        <div className="px-3.5 pb-2">
          <EvidenceList targets={targets} activeAnchor={activeAnchor} onLocate={onLocate} />
        </div>
      )}

      {/*
       * 冲突的两侧取值就地摆开：复核队列里最费时间的动作是「来回切文件比两个值」，
       * 把候选值、来源文件名、页码一次性列在这里，裁决就能在这张卡内完成。
       * 系统仍然不替用户选（见 03 第 4.5 节），只负责把选项摆到眼前。
       */}
      {conflict !== null && conflict.status === "open" && (
        <div className="border-t border-rose-200 bg-rose-50 px-3.5 py-2">
          <p className="text-[13px] font-medium text-rose-800">
            同一字段在其它文件里抽出了不同的值，需要裁定
          </p>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {conflict.candidates.map((candidate) => (
              <li
                key={candidate.id}
                className="flex items-start justify-between gap-3 border border-rose-100 bg-white px-2 py-1.5"
              >
                <span className="min-w-0 flex-1">
                  <span className={DATA_CLASS + " block text-[16px] leading-6 break-words text-slate-900"}>
                    {candidate.value_text || "（空值）"}
                  </span>
                  <span className="mt-0.5 block truncate text-[13px] text-slate-500">
                    {candidate.display_name}
                    {candidate.page_no !== null ? " · 第 " + candidate.page_no + " 页" : ""}
                  </span>
                </span>
                <button
                  type="button"
                  disabled={busy || conflictBusy}
                  onClick={() => void decideConflict(candidate.id)}
                  className={BUTTON_CLASS + " shrink-0"}
                >
                  采用这条
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {attemptsOpen && (
        <div className="px-3.5 pb-2.5">
          <AttemptHistory
            attempts={attempts ?? []}
            loading={attemptsLoading}
            error={attemptsError}
            onLocate={onLocate}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5 border-t border-slate-100 px-3.5 py-2">
        {isNotFound ? (
          <>
            <button type="button" className={PRIMARY_BUTTON_CLASS} disabled={busy} onClick={submitConfirm}>
              确认没有
            </button>
            <button
              type="button"
              className={BUTTON_CLASS}
              disabled={busy}
              onClick={() => beginEdit("supplement")}
            >
              人工补充
            </button>
          </>
        ) : (
          <>
            <button type="button" className={PRIMARY_BUTTON_CLASS} disabled={busy} onClick={submitConfirm}>
              确认
            </button>
            <button
              type="button"
              className={BUTTON_CLASS}
              disabled={busy}
              onClick={() => beginEdit("correct")}
            >
              修正
            </button>
            {rerunButton !== "hide" && (
              <button
                type="button"
                className={BUTTON_CLASS}
                disabled={busy}
                onClick={() => setRerunOpen((open) => !open)}
              >
                重跑
              </button>
            )}
            <button type="button" className={DANGER_GHOST_BUTTON_CLASS} disabled={busy} onClick={submitReject}>
              驳回
            </button>
          </>
        )}
      </div>

      {!isNotFound && rerunButton === "show_hint" && (
        <p className="border-t border-amber-100 bg-amber-50 px-3.5 py-1.5 text-[13px] text-amber-800">
          这个字段重跑一次通常能修好
        </p>
      )}

      {rerunButton === "hide" && !isNotFound && !rerunOpen && (
        <button
          type="button"
          className="border-t border-slate-100 px-3.5 py-1.5 text-left text-[13px] text-slate-400 hover:text-slate-600 hover:underline"
          onClick={() => setRerunOpen(true)}
          disabled={busy}
        >
          该字段重跑通常无用，仍要重跑
        </button>
      )}

      {rerunOpen && (
        <div className="flex flex-col gap-2 border-t border-slate-200 bg-slate-50 px-3.5 py-2.5">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] text-slate-500">
              重跑时给模型的提示（可留空，留空即普通重跑）
            </span>
            <input
              ref={rerunInputRef}
              value={rerunHint}
              onChange={(event) => setRerunHint(event.target.value)}
              placeholder="例如：该值可能在「投标人须知前附表」或「评标办法」章节"
              className={INPUT_CLASS}
            />
          </label>
          <div className="flex gap-1.5">
            <button type="button" className={PRIMARY_BUTTON_CLASS} disabled={busy} onClick={() => void submitRerun()}>
              提交重跑
            </button>
            <button
              type="button"
              className={BUTTON_CLASS}
              disabled={busy}
              onClick={() => setRerunOpen(false)}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {editMode !== null && (
        <div className="flex flex-col gap-2.5 border-t border-sky-200 bg-sky-50 px-3.5 py-2.5">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] text-slate-500">
              {editMode === "supplement" ? "补充的值" : "修正后的值"}
            </span>
            <input
              autoFocus
              value={draftValue}
              onChange={(event) => setDraftValue(event.target.value)}
              placeholder="填写修正后的值"
              className={INPUT_CLASS}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] text-slate-500">原文位置（锚点，已按当前证据预填）</span>
            <input
              value={draftAnchor}
              onChange={(event) => setDraftAnchor(event.target.value)}
              placeholder="例如 p12b5"
              className={INPUT_CLASS + " " + DATA_CLASS}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] text-slate-500">该位置的原文片段（选填，便于复核时比对）</span>
            <textarea
              value={draftQuote}
              onChange={(event) => setDraftQuote(event.target.value)}
              rows={2}
              className={INPUT_CLASS}
            />
          </label>
          <div className="flex gap-1.5">
            <button
              type="button"
              className={PRIMARY_BUTTON_CLASS}
              disabled={busy || !draftValue.trim() || !draftAnchor.trim()}
              onClick={() => void submitEdit()}
            >
              提交{editMode === "supplement" ? "补充" : "修正"}
            </button>
            <button
              type="button"
              className={GHOST_BUTTON_CLASS}
              disabled={busy}
              onClick={() => setEditMode(null)}
            >
              取消
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
