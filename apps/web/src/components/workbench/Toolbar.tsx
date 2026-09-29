"use client";

/**
 * 工具栏：站点导航（工作台 / 模型管理）+ 项目导出 + 页码跳转 + 缩放
 * （见 docs/设计/06 第 2 节、12 第 8 节）。
 *
 * 页码输入用「草稿 + 提交」而不是受控于 currentPage：用户输入到一半时，
 * 滚动位置可能被一次定位改动，受控回写会把他正在敲的数字冲掉。
 *
 * 搜索与证据过滤留待后续切片；缩放入口保留「适应宽度」，因为它是回到默认状态的唯一出口。
 */

import { useState } from "react";

import { AppNav } from "@/components/AppNav";
import { useViewerStore } from "@/lib/store/viewerStore";

import { ExportButton } from "./ExportButton";

interface Props {
  pageCount: number;
  /** 静态样本没有项目：导出按钮按不可用展示，而不是消失（用户要能看出差在哪）。 */
  projectId: number | null;
  onNotice: (message: string | null) => void;
}

export function Toolbar({ pageCount, projectId, onNotice }: Props) {
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
      {/* 顶栏左侧的导航与模型管理页共用一份实现（设计文档 12 第 8 节） */}
      <AppNav />
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

      <ExportButton projectId={projectId} onNotice={onNotice} />

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