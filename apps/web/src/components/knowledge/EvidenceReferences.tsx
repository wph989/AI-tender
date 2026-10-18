"use client";

import { Popover } from "antd";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import type { Citation } from "@/types/knowledge";

/** 同页可有不同条件，依据按块与摘录保留；先看出处和摘录再决定跳到哪一处。 */
export function EvidenceReferences({ refs, onLocate }: {
  refs: Citation[]; onLocate: (ref: Citation) => void;
}) {
  const [open, setOpen] = useState(false);
  const distinct = [...new Map(refs.map((ref) => [
    [ref.source_id, ref.version_id, ref.parse_run_id, ref.element_id, ref.quote].join("\u0000"), ref,
  ])).values()];
  const first = distinct[0];
  if (!first) return null;
  const where = (ref: Citation) => `${ref.file_name} · ${ref.page_no ? `第 ${ref.page_no} 页` : "原文"}`;
  if (distinct.length === 1) return <span className="value-locates" role="group" aria-label="原文依据">
    <button type="button" title={where(first) + "：" + first.quote}
      aria-label={"定位：" + where(first)} onClick={() => onLocate(first)}>
      <Icon name="target" size={13} /><span className="evidence-file">{first.file_name}</span>
      <span>{first.page_no ? `第 ${first.page_no} 页` : "查看原文"}</span>
    </button>
  </span>;
  return <span className="value-locates" role="group" aria-label="原文依据">
    <Popover trigger="click" open={open} onOpenChange={setOpen} placement="bottomLeft"
      content={<section className="evidence-picker" aria-label="选择原文依据">
        <p>各处依据共同支持本事项，点击摘录打开原文。</p>
        <ol>{distinct.map((ref, index) => <li key={index}>
          <button type="button" aria-label={"定位：" + where(ref)} onClick={() => {
            setOpen(false); onLocate(ref);
          }}>
            <strong>{index + 1}. {where(ref)}</strong><span>{ref.quote}</span>
          </button>
        </li>)}</ol>
      </section>}>
      <button type="button" aria-expanded={open} aria-label={`查看 ${distinct.length} 处依据`}>
        <Icon name="target" size={13} />{distinct.length} 处依据
      </button>
    </Popover>
  </span>;
}
