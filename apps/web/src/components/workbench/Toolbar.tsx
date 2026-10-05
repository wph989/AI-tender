"use client";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { BUTTON_CLASS, DATA_CLASS, INPUT_CLASS, GHOST_BUTTON_CLASS } from "@/components/ui";
import { useViewerStore } from "@/lib/store/viewerStore";
import { ExportButton } from "./ExportButton";

interface Props { pageCount: number; projectId: number | null; onNotice: (message: string | null) => void; showExport?: boolean; }

/** 页码草稿独立于滚动位置，避免用户输入时被当前页同步覆盖。 */
export function Toolbar({ pageCount, projectId, onNotice, showExport = true }: Props) {
  const [draft, setDraft] = useState("");
  const zoom = useViewerStore((state) => state.zoom);
  const setZoom = useViewerStore((state) => state.setZoom);
  const currentPage = useViewerStore((state) => state.currentPage);
  const requestJump = useViewerStore((state) => state.requestJump);
  const jump = (raw: number) => {
    if (!pageCount || !Number.isFinite(raw)) return;
    requestJump(Math.min(Math.max(1, Math.trunc(raw)), pageCount));
    setDraft("");
  };
  return (
    <div className="workbench-toolbar">
      <span className="toolbar-title mr-3 flex items-center gap-2 text-[13px] font-semibold"><Icon name="book" size={16} />文档原文</span>
      <div className="flex items-center gap-1">
        <button type="button" className={GHOST_BUTTON_CLASS} disabled={currentPage <= 1 || !pageCount} aria-label="上一页" onClick={() => jump(currentPage - 1)}><Icon name="chevron" size={14} className="rotate-180" /></button>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && draft.trim()) jump(Number(draft)); }} onBlur={() => { if (draft.trim()) jump(Number(draft)); }} placeholder={String(currentPage)} inputMode="numeric" aria-label="跳转到页码" className={INPUT_CLASS + " w-12 text-center " + DATA_CLASS} />
        <span className="px-1 text-[12px] text-slate-400">/ {pageCount}</span>
        <button type="button" className={GHOST_BUTTON_CLASS} disabled={currentPage >= pageCount} aria-label="下一页" onClick={() => jump(currentPage + 1)}><Icon name="chevron" size={14} /></button>
      </div>
      <div className="ml-auto flex items-center gap-1">
        <button type="button" className={GHOST_BUTTON_CLASS} aria-label="缩小" onClick={() => setZoom(zoom - .1)}>−</button>
        <span className={DATA_CLASS + " w-11 text-center text-[12px] text-slate-500"}>{Math.round(zoom * 100)}%</span>
        <button type="button" className={GHOST_BUTTON_CLASS} aria-label="放大" onClick={() => setZoom(zoom + .1)}>＋</button>
        <button type="button" className={BUTTON_CLASS + " toolbar-fit ml-2 py-1.5"} onClick={() => setZoom(1)}>适应宽度</button>
      </div>
      {showExport && <ExportButton projectId={projectId} onNotice={onNotice} />}
    </div>
  );
}
