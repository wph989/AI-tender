"use client";

/**
 * 配置版本面板：版本列表 + 详情（diff / 影响清单逐条确认 / 门禁 / 审计）。
 *
 * 门禁的关键是"每条影响单独确认"（设计文档 09 第 7.1 节）：这里不给"全部确认"按钮，
 * 一次点击就能过掉的确认等同于没有确认——门禁事后要能回答"谁看了哪一条"。
 */

import { useState } from "react";

import { BUTTON_CLASS, DANGER_BUTTON_CLASS, INPUT_CLASS, PRIMARY_BUTTON_CLASS } from "@/components/ui";
import {
  blockerLabel,
  diffRows,
  formatValue,
  impactKindLabel,
  releaseStatusLabel,
} from "@/lib/config/draft";
import { formatTime } from "@/lib/llm/format";
import type { ConfigRelease, ConfigReleaseDetail, ImpactEntry } from "@/types/config";

interface Props {
  releases: ConfigRelease[];
  detail: ConfigReleaseDetail | null;
  busy: boolean;
  onSelect: (id: number) => void;
  onAcknowledge: (entry: ImpactEntry, comment: string) => Promise<void>;
  onActivate: (force: boolean, reason: string) => Promise<void>;
  onRollback: (reason: string) => Promise<void>;
}

/** 状态的圆点色。为什么不用药丸：一列版本号各顶一个填色胶囊，眼睛会被色块带走，
 *  反而读不到版本号本身；圆点的重量刚好够把六种状态区分开。 */
const STATUS_DOT_CLASS: Record<string, string> = {
  draft: "bg-amber-500",
  active: "bg-emerald-500",
  archived: "bg-slate-400",
  rolled_back: "bg-rose-500",
};

const STATUS_TEXT_CLASS: Record<string, string> = {
  draft: "text-amber-700",
  active: "text-emerald-700",
  archived: "text-slate-500",
  rolled_back: "text-rose-700",
};

export function ReleasePanel({
  releases,
  detail,
  busy,
  onSelect,
  onAcknowledge,
  onActivate,
  onRollback,
}: Props) {
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");

  const isDraft = detail?.status === "draft";
  const softBreaches = detail?.gate.soft_breaches ?? [];
  const rows = detail === null ? [] : diffRows(detail.changed);
  const unacked = detail?.impact.filter((entry) => !entry.acked).length ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <section className="border border-slate-200 bg-white px-5 py-4">
        <h2 className="font-serif text-[19px] leading-[28px] text-slate-900">配置版本</h2>
        <p className="mt-1 text-[13px] leading-5 text-slate-500">
          回滚是把历史版本直接置回生效，不重建配置（避免遗漏）。
        </p>
        <ul className="mt-3 flex flex-col divide-y divide-slate-100">
          {releases.map((release) => (
            <li key={release.id}>
              <button
                type="button"
                className={
                  "flex w-full flex-wrap items-center gap-2 py-2 text-left hover:bg-slate-50 " +
                  (detail?.id === release.id ? "bg-slate-50" : "")
                }
                onClick={() => onSelect(release.id)}
              >
                <span className="w-12 text-[13px] text-slate-500">v{release.version_no}</span>
                <span
                  className={
                    "inline-flex items-center gap-1.5 text-[13px] " +
                    (STATUS_TEXT_CLASS[release.status] ?? "text-slate-500")
                  }
                >
                  <span
                    aria-hidden
                    className={
                      "h-1.5 w-1.5 rounded-full " +
                      (STATUS_DOT_CLASS[release.status] ?? "bg-slate-400")
                    }
                  />
                  {releaseStatusLabel(release.status)}
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-slate-600">
                  {release.note ?? "—"}
                </span>
                <span className="text-[11px] text-slate-400">
                  {release.created_by} · {formatTime(release.created_at)}
                </span>
              </button>
            </li>
          ))}
          {releases.length === 0 && <li className="py-2 text-[13px] text-slate-500">还没有配置版本。</li>}
        </ul>
      </section>

      {detail !== null && (
        <section className="border border-slate-200 bg-white px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-serif text-[19px] leading-[28px] text-slate-900">v{detail.version_no} 详情</h2>
            <span
              className={
                "inline-flex items-center gap-1.5 text-[13px] " +
                (STATUS_TEXT_CLASS[detail.status] ?? "text-slate-500")
              }
            >
              <span
                aria-hidden
                className={
                  "h-1.5 w-1.5 rounded-full " + (STATUS_DOT_CLASS[detail.status] ?? "bg-slate-400")
                }
              />
              {releaseStatusLabel(detail.status)}
            </span>
            {detail.based_on !== null && (
              <span className="text-[11px] text-slate-400">基于版本 #{detail.based_on}</span>
            )}
            {isDraft && unacked > 0 && (
              <span className="text-[11px] text-amber-700">还有 {unacked} 条影响未确认</span>
            )}
          </div>

          <h3 className="mt-3 font-serif text-[14px] text-slate-800">与当前生效版本的差异</h3>
          {rows.length === 0 ? (
            <p className="mt-1 text-[13px] leading-5 text-slate-500">没有差异。</p>
          ) : (
            <table className="mt-1 w-full text-[13px]">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[13px] text-slate-400">
                  <th className="border-b border-slate-200 py-2">配置项</th>
                  <th className="border-b border-slate-200 py-2">原值</th>
                  <th className="border-b border-slate-200 py-2">新值</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} className="border-t border-slate-100">
                    <td className="border-b border-slate-100 py-1 pr-2">
                      <code>{row.key}</code>
                    </td>
                    <td className="py-1 pr-2 text-slate-500">{formatValue(row.old)}</td>
                    <td className="py-1 text-slate-800">{formatValue(row.new)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3 className="mt-4 font-serif text-[14px] text-slate-800">变更影响清单</h3>
          <p className="mt-1 text-[13px] leading-5 text-slate-500">
            必须逐条确认"已知悉"，每条单独落一行确认记录（谁、何时、确认了哪一条）。
          </p>
          <ul className="mt-2 flex flex-col gap-1">
            {detail.impact.map((entry) => (
              <li
                key={entry.kind + "|" + entry.ref}
                className="flex flex-wrap items-center gap-2 border border-slate-200 px-2 py-1"
              >
                <span className="w-24 text-[11px] text-slate-500">
                  {impactKindLabel(entry.kind)}
                </span>
                <code className="min-w-0 flex-1 truncate text-[13px]">{entry.ref}</code>
                {entry.acked ? (
                  <span className="text-[11px] text-emerald-700">已确认</span>
                ) : (
                  <button
                    type="button"
                    className={BUTTON_CLASS}
                    disabled={busy || !isDraft}
                    onClick={() => void onAcknowledge(entry, comment)}
                  >
                    确认已知悉
                  </button>
                )}
              </li>
            ))}
            {detail.impact.length === 0 && (
              <li className="text-[13px] text-slate-500">本次变更没有影响条目。</li>
            )}
          </ul>
          {detail.impact.length > 0 && (
            <input
              className={INPUT_CLASS + " mt-2 w-full"}
              placeholder="确认备注（可选，会写进审计）"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          )}

          <h3 className="mt-4 font-serif text-[14px] text-slate-800">门禁</h3>
          {detail.gate.passed ? (
            <p className="mt-1 text-[13px] text-emerald-700">当前满足激活条件。</p>
          ) : (
            <ul className="mt-1 flex flex-col gap-0.5 text-[13px]">
              {detail.gate.blockers.map((code) => (
                <li key={code} className="text-rose-700">
                  阻断：{blockerLabel(code)}
                </li>
              ))}
              {softBreaches.map((code) => (
                <li key={code} className="text-amber-700">
                  需二次确认：{blockerLabel(code)}
                </li>
              ))}
            </ul>
          )}

          {isDraft && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                className={INPUT_CLASS + " min-w-64 flex-1"}
                placeholder={
                  softBreaches.length > 0 ? "强制激活必须填写理由" : "激活理由（可选）"
                }
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <button
                type="button"
                className={PRIMARY_BUTTON_CLASS}
                disabled={
                  busy ||
                  detail.gate.blockers.length > 0 ||
                  (softBreaches.length > 0 && reason.trim() === "")
                }
                onClick={() => void onActivate(softBreaches.length > 0, reason)}
              >
                {softBreaches.length > 0 ? "强制激活" : "激活"}
              </button>
            </div>
          )}

          {detail.status !== "draft" && detail.status !== "active" && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                className={INPUT_CLASS + " min-w-64 flex-1"}
                placeholder="回滚理由（可选）"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <button
                type="button"
                className={DANGER_BUTTON_CLASS}
                disabled={busy}
                onClick={() => void onRollback(reason)}
              >
                回滚到该版本
              </button>
            </div>
          )}

          <h3 className="mt-4 font-serif text-[14px] text-slate-800">审计</h3>
          <ul className="mt-1 flex flex-col gap-0.5 text-[13px] text-slate-600">
            {detail.audit.map((entry) => (
              <li key={entry.id}>
                {formatTime(entry.created_at)} · {entry.actor} · {entry.action}
                {entry.reason !== null && entry.reason !== "" ? " · " + entry.reason : ""}
              </li>
            ))}
            {detail.audit.length === 0 && <li className="text-slate-500">暂无审计记录。</li>}
          </ul>
        </section>
      )}
    </div>
  );
}
