"use client";

/**
 * 工具栏：页码跳转 + 缩放（见 docs/设计/06 第 2 节组件树）。
 *
 * 页码输入用「草稿 + 提交」而不是受控于 currentPage：用户输入到一半时，
 * 滚动位置可能被一次定位改动，受控回写会把他正在敲的数字冲掉。
 *
 * 搜索与证据过滤留待后续切片；缩放入口保留「适应宽度」，因为它是回到默认状态的唯一出口。
 */

import { useState } from "react";

import { useViewerStore } from "@/lib/store/viewerStore";

interface Props {
  pageCount: number;
}

export function Toolbar({ pageCount }: Props) {
  const [draft, setDraft] = useState("");
  const zoom = useViewerStore((state) => state.zoom);
  const setZoom = useViewerStore((state) => state.setZoom);
  const currentPage = useViewerStore((state) => state.currentPage);
  const requestJump = useViewerStore((state) => state.requestJump);

  const jump = (raw: number) => {
    if (pageCount === 0 || !Number.isFinite(raw)) return;
    requestJump(Math.min(Math.max(1, Math.trunc(raw)), pageCount));
    setDraft("");
  };

  const buttonClass =
    "rounded border border-slate-300 px-2 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40";

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
      <span className="text-sm font-semibold text-slate-800">AI-Tender 招标文件工作台</span>
      <span className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700 ring-1 ring-amber-200">
        阶段 1 · 静态样本数据
      </span>

      <div className="ml-auto flex items-center gap-2 text-sm text-slate-600">
        <span className="tabular-nums">
          第 {currentPage} 页 / 共 {pageCount} 页
        </span>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") jump(Number(draft));
          }}
          inputMode="numeric"
          placeholder="页码"
          className="w-20 rounded border border-slate-300 px-2 py-1 text-sm focus:border-sky-500 focus:outline-none"
        />
        <button type="button" className={buttonClass} disabled={pageCount === 0} onClick={() => jump(Number(draft))}>
          跳转
        </button>
      </div>

      <div className="flex items-center gap-1 text-sm text-slate-600">
        <button type="button" className={buttonClass} onClick={() => setZoom(zoom - 0.1)}>
          −
        </button>
        <span className="w-12 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
        <button type="button" className={buttonClass} onClick={() => setZoom(zoom + 0.1)}>
          ＋
        </button>
        <button type="button" className={buttonClass} onClick={() => setZoom(1)}>
          适应宽度
        </button>
      </div>
    </header>
  );
}