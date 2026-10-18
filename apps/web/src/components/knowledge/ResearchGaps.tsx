"use client";

import { Typography } from "antd";
import { Icon } from "@/components/Icon";
import { groupGaps, type DisplayGap } from "@/lib/analysis/gaps";

export function ResearchGaps({ gaps = [], expanded = false, onNavigate }: {
  gaps?: DisplayGap[];
  expanded?: boolean;
  onNavigate?: (gap: DisplayGap) => void;
}) {
  const groups = groupGaps(gaps);
  if (!groups.length) return null;
  const body = <ul className="research-gap-list">{groups.map((group) => {
    const first = group.gaps[0]!;
    return <li key={group.key}>
      <div className="gap-identity"><strong>{group.category}</strong>
        <span>{[first.moduleTitle, first.topicTitle].filter(Boolean).join(" · ") || "当前专题"}</span></div>
      {first.scopeLabel && <p className="research-gap-scope">{first.scopeLabel}</p>}
      {group.gaps.map((gap) => <Typography.Paragraph key={gap.key} ellipsis={{
        rows: 3, expandable: "collapsible", symbol: (open) => open ? "收起" : "展开说明",
      }}>{gap.detail}</Typography.Paragraph>)}
      {group.category === "分析尚未完成" && <p className="gap-guidance">这是分析进度缺口，不代表原文没有要求。</p>}
      {group.category === "结构化待完善" && <p className="gap-guidance">已有内容保留；使用数量、边界或条件前请结合原文核对。</p>}
      {onNavigate && (first.moduleKey || first.recordId) && <button type="button" className="gap-jump"
        onClick={() => onNavigate(first)}>{first.recordId ? "查看相关事项" : "前往所属专题"}</button>}
    </li>;
  })}</ul>;
  if (expanded) return <section className="research-gaps gap-board" aria-label="待核对事项">
    <p className="gap-board-intro">按原因、专题和适用范围归并为 {groups.length} 组，保留各项说明。</p>{body}
  </section>;
  return <details className="research-gaps"><summary>
    <Icon name="alert" size={17} /><span className="research-gaps-heading">
      <strong>有 {groups.length} 组内容待核对</strong><span>按专题与原因查看，进度缺口单独标明。</span>
    </span><span className="research-gaps-toggle"><span className="research-gaps-show">查看事项</span>
      <span className="research-gaps-hide">收起事项</span><Icon name="chevron" size={14} /></span>
  </summary>{body}</details>;
}
