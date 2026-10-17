"use client";

import { Typography } from "antd";
import { Icon } from "@/components/Icon";

export function ResearchGaps({ gaps }: { gaps?: { key: string; detail: string; scopeLabel?: string }[] }) {
  if (!gaps?.length) return null;

  // 缺口提醒与分析过程分开，避免用户把尚未确认的内容当成已核实结论。
  return (
    <details className="research-gaps">
      <summary>
        <Icon name="alert" size={17} />
        <span className="research-gaps-heading">
          <strong>有 {gaps.length} 项内容待核对</strong>
          <span>分析时未能确认的内容，请核对原文或补充材料。</span>
        </span>
        <span className="research-gaps-toggle">
          <span className="research-gaps-show">查看事项</span>
          <span className="research-gaps-hide">收起事项</span>
          <Icon name="chevron" size={14} />
        </span>
      </summary>
      <ul className="research-gap-list">
        {gaps.map((gap) => (
          <li key={gap.key}>
            {gap.scopeLabel && <p className="research-gap-scope">{gap.scopeLabel}</p>}
            {/* 按可见行数折叠，保留完整说明供核对，不猜测或改写模型给出的缺口。 */}
            <Typography.Paragraph ellipsis={{
              rows: 2,
              expandable: "collapsible",
              symbol: (expanded) => expanded ? "收起" : "展开说明",
            }}>
              {gap.detail}
            </Typography.Paragraph>
          </li>
        ))}
      </ul>
    </details>
  );
}
