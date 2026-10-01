"use client";

/**
 * 复核统计条（通栏）：项目级的复核进度 + 「复核队列 / 全部结果」两档开关。
 *
 * 三个数字的口径（见 docs/设计/06 第 11 节）：
 *   已复核  reviewed        项目内被人处理过（确认/修正/补充/驳回）的结果条数；
 *   已修正  corrected       其中被人工改过值的——**这一项必须显示**：
 *                           它是「这份抽取结果到底有多不可信」的唯一直接证据；
 *   待复核  pending_review  后端统计出的待处理条数，点它直接切到复核队列。
 *
 * 为什么不显示「/ 共 N」分母：GET /projects/{id}/stats 不返回「项目内结果实例总数」，
 * 前端自己拼分母会拼出「分母 < 已复核」这种自相矛盾的数字。宁可少给一个数，
 * 也不能给一个错的（已记入 HANDOVER 与 docs/设计/06 的偏离清单）。
 *
 * 统计是旁路信息：接口失败就安静地不显示，绝不因为统计取不到而挡住核对。
 */

import { useEffect, useState } from "react";

import { DATA_CLASS, EYEBROW_CLASS } from "@/components/ui";
import { loadProjectStats, type ProjectStats } from "@/lib/api/client";

interface Props {
  projectId: number | null;
  /** 复核模式由工作台持有，统计条只是它的一个入口（点「待复核」即进入）。 */
  reviewOnly: boolean;
  onReviewModeChange: (next: boolean) => void;
  /** 复核/重跑后自增，用来重新取数：计数器不能停在旧值上。 */
  refreshToken: number;
}

function Dot() {
  return (
    <span aria-hidden className="text-slate-300">
      ·
    </span>
  );
}

export function ReviewStatsBar({ projectId, reviewOnly, onReviewModeChange, refreshToken }: Props) {
  const [stats, setStats] = useState<ProjectStats | null>(null);

  useEffect(() => {
    if (projectId === null) {
      setStats(null);
      return;
    }
    let alive = true;
    loadProjectStats(projectId)
      .then((loaded) => {
        if (alive) setStats(loaded);
      })
      .catch(() => {
        if (alive) setStats(null);
      });
    return () => {
      alive = false;
    };
  }, [projectId, refreshToken]);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-200 bg-white px-4 py-2">
      <span className={EYEBROW_CLASS}>复核进度</span>

      {stats === null ? (
        <span className="text-[13px] text-slate-400">暂无统计数据</span>
      ) : (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-slate-600">
          <span>
            已复核{" "}
            <span className={DATA_CLASS + " text-[17px] text-slate-900"}>{stats.reviewed}</span>
          </span>
          <Dot />
          <span>
            已修正{" "}
            <span
              className={
                DATA_CLASS +
                " text-[17px] " +
                (stats.corrected > 0 ? "text-indigo-700" : "text-slate-400")
              }
            >
              {stats.corrected}
            </span>
          </span>
          <Dot />
          {stats.pending_review > 0 && !reviewOnly ? (
            <button
              type="button"
              onClick={() => onReviewModeChange(true)}
              title="切到结果面板的复核队列，先处理这些"
              className="rounded-[2px] px-1 text-slate-600 hover:bg-amber-50 hover:text-slate-900"
            >
              待复核{" "}
              <span className={DATA_CLASS + " mark-ink px-1 text-[17px] text-slate-900"}>
                {stats.pending_review}
              </span>
            </button>
          ) : (
            <span>
              待复核{" "}
              <span className={DATA_CLASS + " text-[17px] text-slate-400"}>
                {stats.pending_review}
              </span>
            </span>
          )}
        </div>
      )}

      {reviewOnly && (
        <span className="ml-auto shrink-0 text-[13px] text-slate-400">
          结果面板正按复核队列排序
        </span>
      )}
    </div>
  );
}