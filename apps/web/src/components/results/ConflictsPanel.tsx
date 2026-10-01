"use client";

/**
 * 跨文件冲突裁定：同一字段在不同文件里抽出了不同的值，必须由人选一个。
 *
 * 为什么做成自取数的小面板：冲突是项目级概念，而工作台是按版本打开的；
 * 把它挂在结果面板头部，用户一眼能看到「还有 2 处矛盾没处理」，
 * 不用切到别的页面才发现导出里混着两个值。
 *
 * 系统不替用户选：两个值都摆出来（含文件名与页码），后出文件的值只标「可能覆盖」，
 * 不自动采信——裁定是谁做的，比裁定得快更重要（见 03 第 4.5 节）。
 */

import { useCallback, useEffect, useState } from "react";

import { BUTTON_CLASS, DATA_CLASS } from "@/components/ui";
import { loadConflicts, resolveConflict } from "@/lib/api/client";
import type { WireConflict } from "@/types/workbench";

interface Props {
  projectId: number | null;
  onNotice: (message: string | null) => void;
  onResolved: () => Promise<void>;
}

export function ConflictsPanel({ projectId, onNotice, onResolved }: Props) {
  const [open, setOpen] = useState(false);
  const [conflicts, setConflicts] = useState<WireConflict[] | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (projectId === null) {
      setConflicts([]);
      return;
    }
    try {
      setConflicts(await loadConflicts(projectId));
    } catch (error: unknown) {
      onNotice(error instanceof Error ? error.message : "冲突列表加载失败");
    }
  }, [projectId, onNotice]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const decide = async (
    conflict: WireConflict,
    action: "resolve" | "dismiss",
    resolvedId: number | null,
  ) => {
    setBusyId(conflict.id);
    onNotice(null);
    try {
      await resolveConflict(conflict.id, { action, resolved_id: resolvedId });
      await refresh();
      await onResolved();
    } catch (error: unknown) {
      onNotice(error instanceof Error ? error.message : "冲突裁定失败");
    } finally {
      setBusyId(null);
    }
  };

  if (projectId === null || conflicts === null) return null;
  const openCount = conflicts.filter((item) => item.status === "open").length;

  return (
    <div className="mt-2.5">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={
          "relative flex w-full items-center gap-2 border px-2.5 py-1.5 text-left text-[13px] " +
          (openCount > 0
            ? "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
            : "border-slate-200 bg-slate-50 text-slate-500 hover:bg-slate-100")
        }
      >
        {openCount > 0 && (
          <span aria-hidden className="absolute inset-y-0 left-0 w-[4px] bg-rose-500" />
        )}
        <span className="font-medium">跨文件冲突</span>
        <span className={DATA_CLASS + " text-[13px]"}>
          {openCount > 0 ? openCount + " 项待裁定" : "无待裁定"}
        </span>
        <span className="ml-auto text-[13px] text-slate-400">{open ? "收起" : "展开"}</span>
      </button>

      {open && (
        <div className="mt-2 flex flex-col gap-2">
          {conflicts.length === 0 && (
            <p className="text-[13px] text-slate-500">当前项目没有跨文件冲突。</p>
          )}
          {conflicts.map((conflict) => (
            <div key={conflict.id} className="border border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-100 px-2.5 py-1.5">
                <span className="text-[13px] font-medium text-slate-800">
                  {conflict.field_label}
                </span>
                <span className="text-[13px] text-slate-500">
                  {conflict.status === "open" ? "待裁定" : "已处理"}
                </span>
              </div>

              {conflict.status === "open" ? (
                <div className="px-2.5 py-2">
                  <ul className="flex flex-col gap-1.5">
                    {conflict.candidates.map((candidate) => (
                      <li
                        key={candidate.id}
                        className="flex items-start justify-between gap-3 bg-slate-50 px-2 py-1.5"
                      >
                        <span className="min-w-0 flex-1">
                          <span className={DATA_CLASS + " block text-[14px] break-words text-slate-900"}>
                            {candidate.value_text || "（空值）"}
                          </span>
                          <span className="mt-0.5 block truncate text-[13px] text-slate-500">
                            {candidate.display_name}
                            {candidate.page_no !== null ? ` · 第 ${candidate.page_no} 页` : ""}
                          </span>
                        </span>
                        <button
                          type="button"
                          disabled={busyId === conflict.id}
                          onClick={() => void decide(conflict, "resolve", candidate.id)}
                          className={BUTTON_CLASS + " shrink-0"}
                        >
                          采用这条
                        </button>
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    disabled={busyId === conflict.id}
                    onClick={() => void decide(conflict, "dismiss", null)}
                    className="mt-2 text-[13px] text-slate-500 hover:text-slate-900 hover:underline disabled:opacity-40"
                  >
                    忽略（确认不是真冲突）
                  </button>
                </div>
              ) : (
                <p className="px-2.5 py-2 text-[13px] text-slate-500">
                  已裁定：
                  {conflict.candidates.find((item) => item.id === conflict.resolved_id)
                    ?.value_text ?? "忽略"}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
