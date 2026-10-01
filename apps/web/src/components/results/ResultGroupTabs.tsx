"use client";

/**
 * 分组标签栏（见 docs/设计/06 第 2.1 节）。
 *
 * 为什么是标签而不是一列到底：一个项目 500+ 条结果，滚动列表会让用户「找某组字段」变成体力活；
 * 标签把内容按业务分组隔开，一次只呈现一组，滚动长度可控。
 *
 * 为什么键盘 ←/→ 直接切换（选择即激活）：面板只有一块内容区，多一次回车确认没有任何收益。
 * 交互服从 WAI-ARIA tabs 模式：焦点移到哪个标签，就展示哪个标签的面板。
 *
 * 待复核/冲突的分组在标签上点亮琥珀色圆点：用户不用逐个标签点开找问题。
 *
 * 形态是下划线式而不是药丸式：标签在这里等于「书里的一章」，跟随正文的一条底线
 * 已经足够说明它被选中；药丸会在右栏里再堆一层彩色块，和结果状态的点抢注意力。
 */

import { useRef } from "react";
import type { KeyboardEvent } from "react";

import { DATA_CLASS } from "@/components/ui";
import type { ResultTab } from "@/lib/results/grouping";

interface Props {
  tabs: readonly ResultTab[];
  activeKey: string;
  onSelect: (key: string) => void;
}

export function ResultGroupTabs({ tabs, activeKey, onSelect }: Props) {
  const buttons = useRef(new Map<string, HTMLButtonElement>());

  const selectIndex = (index: number) => {
    const tab = tabs[index];
    if (tab === undefined) return; // noUncheckedIndexedAccess：空标签栏理论上不会走到这里
    onSelect(tab.key);
    // 焦点跟随激活：键盘用户连按 → 不会把焦点留在已隐藏的面板上
    buttons.current.get(tab.key)?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = tabs.length - 1;
    if (event.key === "ArrowRight") selectIndex(index === last ? 0 : index + 1);
    else if (event.key === "ArrowLeft") selectIndex(index === 0 ? last : index - 1);
    else if (event.key === "Home") selectIndex(0);
    else if (event.key === "End") selectIndex(last);
    else return;
    event.preventDefault();
  };

  return (
    <div
      role="tablist"
      aria-label="解析结果分组"
      className="flex gap-0.5 overflow-x-auto border-b border-slate-200 bg-white px-2.5"
    >
      {tabs.map((tab, index) => {
        const active = tab.key === activeKey;
        const title =
          `共 ${tab.items.length} 项` +
          (tab.pending > 0 ? `，${tab.pending} 项待复核` : "") +
          (tab.notFound > 0 ? `，${tab.notFound} 项未找到` : "");
        return (
          <button
            key={tab.key}
            ref={(node) => {
              if (node === null) buttons.current.delete(tab.key);
              else buttons.current.set(tab.key, node);
            }}
            type="button"
            role="tab"
            id={`result-tab-${tab.key}`}
            aria-controls={`result-tabpanel-${tab.key}`}
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            title={title}
            onClick={() => onSelect(tab.key)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={
              "flex shrink-0 items-center gap-1.5 border-b-2 px-2.5 py-2 text-[13px] whitespace-nowrap " +
              "transition-colors " +
              (active
                ? "border-slate-900 font-medium text-slate-900"
                : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800")
            }
          >
            {tab.pending > 0 && (
              <span
                aria-label={`待复核 ${tab.pending} 项`}
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"
              />
            )}
            <span>{tab.label}</span>
            <span
              className={
                DATA_CLASS +
                " text-[13px] " +
                (active ? "text-slate-500" : "text-slate-400")
              }
            >
              {tab.items.length}
            </span>
          </button>
        );
      })}
    </div>
  );
}
