"use client";

/**
 * 章节树（工作台左栏）：解析产出的标题层级，点一条即跳到该章所在页。
 *
 * 为什么要有它：标书动辄上百页，用户想核对「评标办法」这一章时靠拖滚动条是一次盲找；
 * 章节树把「文档结构」这层信息还给用户，定位从「翻」变成「点名」。
 *
 * 为什么默认全部展开：解析出的章节通常只有一两层、几十条，展开仍在一屏内；
 * 默认折叠会让用户先点一下才能看见自己要找的那一章。
 *
 * 为什么当前章用「页码 <= 当前页的最后一个」判定：level 不保证连续、也可能缺父节点，
 * 不能假设树的形状；用「页码单调递增」这一条最稳。
 *
 * 为什么折叠时留一条 36px 的窄脊而不是整体消失：入口消失后用户找不回来，
 * 留一条写着「章节」的脊，等于一个常驻的指路牌。
 */

import { useMemo, useState } from "react";

import { DATA_CLASS, EYEBROW_CLASS } from "@/components/ui";
import type { WireOutlineItem } from "@/types/workbench";

interface Props {
  items: readonly WireOutlineItem[];
  /** 原文视图当前停留的页码。 */
  currentPage: number;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (item: WireOutlineItem) => void;
}

interface FlatNode {
  item: WireOutlineItem;
  depth: number;
  /** element_id 在同一版本内唯一；拼上 anchor 是为了类型上不可能撞号。 */
  key: string;
}

/** 展平成一维：当前章判定、渲染、键盘遍历都只需要一条线性序列。 */
function flatten(
  items: readonly WireOutlineItem[],
  collapsedKeys: ReadonlySet<string>,
  depth: number,
  out: FlatNode[],
): FlatNode[] {
  for (const item of items) {
    const key = item.element_id + ":" + item.anchor;
    out.push({ item, depth, key });
    if (item.children.length > 0 && !collapsedKeys.has(key)) {
      flatten(item.children, collapsedKeys, depth + 1, out);
    }
  }
  return out;
}

const CHEVRON_CLASS =
  "flex h-5 w-5 shrink-0 items-center justify-center rounded-[2px] text-[11px] leading-none " +
  "text-slate-400 hover:bg-slate-100 hover:text-slate-700";

export function OutlineNav({ items, currentPage, collapsed, onToggle, onSelect }: Props) {
  // 记「被折叠的节点」而不是「被展开的」：默认全展开，空集合就是默认状态
  const [collapsedKeys, setCollapsedKeys] = useState<ReadonlySet<string>>(
    () => new Set<string>(),
  );

  const nodes = useMemo(() => flatten(items, collapsedKeys, 0, []), [items, collapsedKeys]);

  const currentKey = useMemo(() => {
    let found: string | null = null;
    for (const node of nodes) {
      if (node.item.page_no <= currentPage) found = node.key;
    }
    return found;
  }, [nodes, currentPage]);

  const toggleNode = (key: string) => {
    setCollapsedKeys((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  };

  if (items.length === 0) return null;

  if (collapsed) {
    return (
      <div className="flex w-9 shrink-0 flex-col items-center gap-2 border-r border-slate-200 bg-white py-2">
        <button
          type="button"
          onClick={onToggle}
          aria-label="展开章节树"
          title="展开章节树"
          className="flex h-6 w-6 items-center justify-center rounded-[2px] border border-slate-300 bg-white text-[13px] leading-none text-slate-600 hover:border-slate-500 hover:bg-slate-50"
        >
          ›
        </button>
        <span className="mt-1 text-[11px] tracking-[0.18em] text-slate-400 [writing-mode:vertical-rl]">
          章节
        </span>
      </div>
    );
  }

  return (
    <nav
      aria-label="章节树"
      className="flex w-[236px] shrink-0 flex-col border-r border-slate-200 bg-white"
    >
      <div className="flex items-center gap-2 border-b border-slate-100 px-3.5 pt-3 pb-2">
        <p className={EYEBROW_CLASS}>章节</p>
        <span className={DATA_CLASS + " text-[11px] text-slate-400"}>{nodes.length}</span>
        <button
          type="button"
          onClick={onToggle}
          aria-label="收起章节树"
          title="收起章节树"
          className="ml-auto flex h-5 w-5 items-center justify-center rounded-[2px] text-[13px] leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          ‹
        </button>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto py-1">
        {nodes.map((node) => {
          const hasChildren = node.item.children.length > 0;
          const isOpen = !collapsedKeys.has(node.key);
          const isCurrent = node.key === currentKey;
          return (
            <li key={node.key} className="relative flex items-center">
              {/* 当前章左侧那道琥珀色条：与结果卡/文件行的卷宗脊同一套「颜色即状态」语法 */}
              {isCurrent && <span aria-hidden className="absolute inset-y-0 left-0 w-[4px] bg-amber-400" />}
              {hasChildren ? (
                <button
                  type="button"
                  className={CHEVRON_CLASS + " ml-1.5"}
                  aria-label={isOpen ? "折叠子章节" : "展开子章节"}
                  aria-expanded={isOpen}
                  onClick={() => toggleNode(node.key)}
                >
                  {isOpen ? "▾" : "▸"}
                </button>
              ) : (
                <span aria-hidden className="ml-1.5 h-5 w-5 shrink-0" />
              )}
              <button
                type="button"
                onClick={() => onSelect(node.item)}
                title={node.item.text + "（第 " + node.item.page_no + " 页）"}
                style={{ paddingLeft: 4 + node.depth * 10 }}
                className={
                  "flex min-w-0 flex-1 items-center gap-2 py-1 pr-2 text-left text-[13px] " +
                  "transition-colors hover:bg-slate-50 " +
                  (isCurrent ? "font-medium text-slate-900" : "text-slate-600")
                }
              >
                <span className="truncate">{node.item.text}</span>
                <span className={DATA_CLASS + " ml-auto shrink-0 text-[11px] text-slate-400"}>
                  {node.item.page_no}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}