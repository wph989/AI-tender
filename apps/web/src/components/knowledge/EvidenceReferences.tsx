"use client";

import { Popover } from "antd";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { groupCitationLocations } from "@/lib/analysis/citations";
import type { Citation } from "@/types/knowledge";

/** 同一位置共用图标；不同原文块分别保留入口，出处与完整摘录可悬停查看。 */
export function EvidenceReferences({ refs, onLocate, inline = false }: {
  refs: Citation[]; onLocate: (ref: Citation) => void; inline?: boolean;
}) {
  const [open, setOpen] = useState(false);
  // 只合并展示；点击仍使用真实引用，不能拼接后冒充原始引文。
  const distinct = groupCitationLocations(refs);
  const first = distinct[0];
  if (!first) return null;
  const where = (ref: Citation) => `${ref.file_name} · ${ref.page_no ? `第 ${ref.page_no} 页` : "原文"}`;
  if (inline) return <span className="value-locates value-locates-inline" role="group" aria-label="本条原文依据">
    {distinct.map(({ ref, quotes }, index) => <button type="button" key={index}
      title={where(ref) + "：" + [...quotes].join("\n\n")}
      aria-label={"定位：" + where(ref) + (distinct.length > 1 ? ` · 依据 ${index + 1}` : "")}
      onClick={() => onLocate(ref)}>
      <Icon name="target" size={14} />
    </button>)}
  </span>;
  if (distinct.length === 1) return <span className="value-locates" role="group" aria-label="原文依据">
    <button type="button" title={where(first.ref) + "：" + [...first.quotes].join("\n\n")}
      aria-label={"定位：" + where(first.ref)} onClick={() => onLocate(first.ref)}>
      <Icon name="target" size={14} />
    </button>
  </span>;
  return <span className="value-locates" role="group" aria-label="原文依据">
    <Popover trigger="click" open={open} onOpenChange={setOpen} placement="bottomLeft"
      content={<section className="evidence-picker" aria-label="选择原文依据">
        <p>各处依据共同支持本事项，点击摘录打开原文。</p>
        <ol>{distinct.map(({ ref, quotes }, index) => <li key={index}>
          <button type="button" aria-label={"定位：" + where(ref)} onClick={() => {
            setOpen(false); onLocate(ref);
          }}>
            <strong>{index + 1}. {where(ref)}</strong><span>{[...quotes].join("\n\n")}</span>
          </button>
        </li>)}</ol>
      </section>}>
      <button type="button" aria-expanded={open} aria-label={`查看 ${distinct.length} 处依据`}
        title={`查看 ${distinct.length} 处依据`}>
        <Icon name="target" size={14} />
      </button>
    </Popover>
  </span>;
}
