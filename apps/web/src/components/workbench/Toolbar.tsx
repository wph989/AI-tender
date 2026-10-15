"use client";
import { Button, Input } from "antd";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { DATA_CLASS } from "@/components/ui";
import { useViewerStore } from "@/lib/store/viewerStore";

interface Props {
  pageCount: number;
}

/** 页码草稿独立于滚动位置，避免用户输入时被当前页同步覆盖。 */
export function Toolbar({
  pageCount,
}: Props) {
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
      <span className="toolbar-title mr-3 flex items-center gap-2 text-[13px] font-semibold">
        <Icon name="book" size={16} />
        文档原文
      </span>
      <div className="flex items-center gap-1">
        <Button
          type="text"
          htmlType="button"
          disabled={currentPage <= 1 || !pageCount}
          aria-label="上一页"
          onClick={() => jump(currentPage - 1)}
        >
          <Icon name="chevron" size={14} className="rotate-180" />
        </Button>
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && draft.trim()) jump(Number(draft));
          }}
          onBlur={() => {
            if (draft.trim()) jump(Number(draft));
          }}
          placeholder={String(currentPage)}
          inputMode="numeric"
          aria-label="跳转到页码"
          className={" w-12 text-center " + DATA_CLASS}
        />
        <span className="px-1 text-[12px] text-slate-400">/ {pageCount}</span>
        <Button
          type="text"
          htmlType="button"
          disabled={currentPage >= pageCount}
          aria-label="下一页"
          onClick={() => jump(currentPage + 1)}
        >
          <Icon name="chevron" size={14} />
        </Button>
      </div>
      <div className="ml-auto flex items-center gap-1">
        <Button
          type="text"
          htmlType="button"
          aria-label="缩小"
          onClick={() => setZoom(zoom - 0.1)}
        >
          −
        </Button>
        <span
          className={
            DATA_CLASS + " w-11 text-center text-[12px] text-slate-500"
          }
        >
          {Math.round(zoom * 100)}%
        </span>
        <Button
          type="text"
          htmlType="button"
          aria-label="放大"
          onClick={() => setZoom(zoom + 0.1)}
        >
          ＋
        </Button>
        <Button
          htmlType="button"
          className={" toolbar-fit ml-2 py-1.5"}
          onClick={() => setZoom(1)}
        >
          适应宽度
        </Button>
      </div>
    </div>
  );
}
