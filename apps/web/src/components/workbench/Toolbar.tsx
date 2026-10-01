"use client";

/**
 * 原文控制条：页码跳转 + 缩放 + 导出（见 docs/设计/06 第 2 节、12 第 8 节）。
 *
 * 这里不放导航：导航在左侧卷宗脊上，工作台是嵌在它右边的。
 * 两处都放导航会让同一个链接在一屏里出现两次，用户会怀疑哪个才是「当前页」。
 *
 * 页码输入用「草稿 + 提交」而不是受控于 currentPage：用户输入到一半时，
 * 滚动位置可能被一次定位改动，受控回写会把他正在敲的数字冲掉。
 *
 * 左侧那个「原文」小字是这一栏的抬头：右栏是「解析结果」，两张纸的标题必须成对出现，
 * 用户才会把它们读成「同一件事的两面」，而不是两个互不相干的列表。
 */

import { useState } from "react";

import { BUTTON_CLASS, DATA_CLASS, EYEBROW_CLASS, INPUT_CLASS } from "@/components/ui";
import { useViewerStore } from "@/lib/store/viewerStore";

import { ExportButton } from "./ExportButton";

interface Props {
  pageCount: number;
  /** 没有项目就没有导出目标：按钮按不可用展示，而不是消失（用户要能看出差在哪）。 */
  projectId: number | null;
  onNotice: (message: string | null) => void;
}

const ZOOM_BUTTON_CLASS =
  "flex h-[26px] w-[26px] items-center justify-center rounded-[2px] border border-slate-300 " +
  "bg-white text-[14px] leading-none text-slate-600 hover:border-slate-500 hover:bg-slate-50 " +
  "disabled:opacity-40 disabled:hover:border-slate-300 disabled:hover:bg-white";

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

  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-200 bg-white px-4 py-2">
      <span className={EYEBROW_CLASS}>原文</span>

      <div className="flex items-center gap-1.5">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") jump(Number(draft));
          }}
          inputMode="numeric"
          placeholder="页码"
          aria-label="跳转到页码"
          className={INPUT_CLASS + " w-[68px] py-1 text-center " + DATA_CLASS}
        />
        <button
          type="button"
          className={BUTTON_CLASS + " py-1"}
          disabled={pageCount === 0}
          onClick={() => jump(Number(draft))}
        >
          跳转
        </button>
        <span className={DATA_CLASS + " ml-1 text-[13px] text-slate-500"}>
          {currentPage} / {pageCount}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          className={ZOOM_BUTTON_CLASS}
          aria-label="缩小"
          onClick={() => setZoom(zoom - 0.1)}
        >
          −
        </button>
        <span className={DATA_CLASS + " w-11 text-center text-[13px] text-slate-500"}>
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          className={ZOOM_BUTTON_CLASS}
          aria-label="放大"
          onClick={() => setZoom(zoom + 0.1)}
        >
          ＋
        </button>
        <button
          type="button"
          className={BUTTON_CLASS + " ml-1 py-1"}
          onClick={() => setZoom(1)}
          title="回到适应宽度"
        >
          适应宽度
        </button>
      </div>

      <span aria-hidden className="h-4 w-px bg-slate-200" />

      <ExportButton projectId={projectId} onNotice={onNotice} />
    </header>
  );
}
