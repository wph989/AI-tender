"use client";

import { Icon } from "@/components/Icon";
import { groupCitationLocations } from "@/lib/analysis/citations";
import type { Citation } from "@/types/knowledge";

/** 每个不同位置都可直接定位；摘录放在提示中，避免定位按钮先变成文本选择器。 */
export function EvidenceReferences({ refs, onLocate, inline = false }: {
  refs: Citation[]; onLocate: (ref: Citation) => void; inline?: boolean;
}) {
  // 只合并展示；点击仍使用真实引用，不能拼接后冒充原始引文。
  const distinct = groupCitationLocations(refs);
  const first = distinct[0];
  if (!first) return null;
  const where = (ref: Citation) => `${ref.file_name} · ${ref.page_no ? `第 ${ref.page_no} 页` : "原文"}`;
  return <span className={"value-locates" + (inline ? " value-locates-inline" : "")}
    role="group" aria-label={inline ? "本条原文依据" : "原文依据"}>
    {distinct.map(({ ref, quotes }, index) => <button type="button" key={index}
      title={where(ref) + "：" + [...quotes].join("\n\n")}
      aria-label={"定位：" + where(ref) + (distinct.length > 1 ? ` · 依据 ${index + 1}` : "")}
      onClick={() => onLocate(ref)}>
      <Icon name="target" size={14} />
    </button>)}
  </span>;
}
