"use client";

/**
 * 字段历史尝试：默认折叠，按需展示旧结果和它们的证据。
 *
 * 为什么独立成组件：历史数据是单字段按需加载的，不能让每张结果卡在首屏都请求一遍尝试链。
 */

import { toBbox } from "@/lib/api/wire";
import { reviewActionLabel, statusLabel, triggerLabel } from "@/lib/results/labels";
import type { EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireAttempt } from "@/types/workbench";

interface Props {
  attempts: readonly WireAttempt[];
  loading: boolean;
  error: string | null;
  onLocate: (target: EvidenceTarget) => void;
}

export function AttemptHistory({ attempts, loading, error, onLocate }: Props) {
  return (
    <section className="mt-2 rounded border border-slate-200 bg-slate-50 p-2">
      <h5 className="text-xs font-medium text-slate-600">尝试链</h5>
      {loading && <p className="mt-2 text-xs text-slate-500">正在加载历史尝试…</p>}
      {error !== null && <p className="mt-2 text-xs text-rose-700">{error}</p>}
      {!loading && error === null && attempts.length === 0 && (
        <p className="mt-2 text-xs text-slate-500">暂无历史尝试</p>
      )}
      {!loading && error === null && attempts.length > 0 && (
        <ol className="mt-2 flex flex-col gap-2">
          {attempts.map((attempt) => (
            <li key={attempt.id} className="border-t border-slate-200 pt-2 first:border-t-0 first:pt-0">
              <div className="flex flex-wrap items-center gap-1 text-xs text-slate-500">
                <span className="font-medium text-slate-700">
                  {attempt.machine_attempt_no === null || attempt.machine_attempt_no === undefined
                    ? "人工"
                    : `第 ${attempt.machine_attempt_no} 次`}
                </span>
                <span>· {triggerLabel(attempt.trigger)}</span>
                {attempt.is_current && (
                  <span className="rounded bg-sky-100 px-1 text-sky-700">当前</span>
                )}
                {attempt.superseded_by_id !== null && attempt.superseded_by_id !== undefined && (
                  <span className="rounded bg-slate-200 px-1 text-slate-600">已被后续结果取代</span>
                )}
                <span>· {statusLabel(attempt.status)}</span>
                {reviewActionLabel(attempt.review_action) !== null && (
                  <span>· {reviewActionLabel(attempt.review_action)}</span>
                )}
              </div>
              <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-800">
                {attempt.value_text || "未找到"}
              </p>
              {attempt.evidence.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {attempt.evidence.map((evidence, index) => {
                    const target: EvidenceTarget = {
                      extractionId: attempt.id,
                      anchor: evidence.anchor,
                      pageNo: evidence.page_no,
                      bbox: toBbox(evidence.bbox),
                      fieldKey: attempt.field_key,
                      label: attempt.field_label ?? attempt.field_key,
                      quote: evidence.quote,
                    };
                    return (
                      <button
                        key={`${evidence.anchor}-${index}`}
                        type="button"
                        onClick={() => onLocate(target)}
                        className="rounded border border-slate-300 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-white"
                      >
                        定位 {evidence.anchor}
                      </button>
                    );
                  })}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
