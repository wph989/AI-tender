"use client";

/**
 * 跨文件冲突裁定：同一字段在不同文件里抽出了不同的值，必须由人选一个。
 *
 * 为什么做成自取数的小面板：冲突是项目级概念，而工作台是按版本打开的；
 * 把它挂在结果面板头部，用户一眼能看到「还有 2 处矛盾没处理」，
 * 不用切到别的页面才发现导出里混着两个值。
 */

import { useCallback, useEffect, useState } from "react";

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
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={
          "rounded border px-2 py-0.5 text-xs " +
          (openCount > 0
            ? "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
            : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100")
        }
      >
        跨文件冲突 {openCount} 项{open ? "（收起）" : ""}
      </button>

      {open && (
        <div className="mt-2 flex flex-col gap-2">
          {conflicts.length === 0 && (
            <p className="text-xs text-slate-500">当前项目没有跨文件冲突。</p>
          )}
          {conflicts.map((conflict) => (
            <div
              key={conflict.id}
              className="rounded border border-slate-200 bg-white px-2 py-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-700">{conflict.field_label}</span>
                <span className="text-slate-500">
                  {conflict.status === "open" ? "待裁定" : "已处理"}
                </span>
              </div>
              {conflict.status === "open" ? (
                <>
                  <ul className="mt-1 flex flex-col gap-1">
                    {conflict.candidates.map((candidate) => (
                      <li
                        key={candidate.id}
                        className="flex items-start justify-between gap-2 rounded bg-slate-50 px-2 py-1"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block font-medium text-slate-800">
                            {candidate.value_text || "（空值）"}
                          </span>
                          <span className="block truncate text-slate-500">
                            {candidate.display_name}
                            {candidate.page_no !== null ? ` · 第 ${candidate.page_no} 页` : ""}
                          </span>
                        </span>
                        <button
                          type="button"
                          disabled={busyId === conflict.id}
                          onClick={() => void decide(conflict, "resolve", candidate.id)}
                          className="shrink-0 rounded border border-sky-300 px-2 py-0.5 text-sky-700 hover:bg-sky-50 disabled:opacity-40"
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
                    className="mt-1 rounded border border-slate-300 px-2 py-0.5 text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                  >
                    忽略（确认不是真冲突）
                  </button>
                </>
              ) : (
                <p className="mt-1 text-slate-500">
                  已裁定：{conflict.candidates.find((item) => item.id === conflict.resolved_id)?.value_text ?? "忽略"}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}