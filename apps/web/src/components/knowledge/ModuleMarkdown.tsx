"use client";

import { Fragment, useMemo, type ReactNode } from "react";
import type { AnalysisField, Citation } from "@/types/knowledge";

/**
 * 解析结果 Markdown 视图：后端字段-值结构由前端按分组拼装成文档式版面。
 * - 字段名即「解析到了什么」，字段下的值即「解析值是什么」，值下方的引用即该值的证据。
 * - 同一字段出现多个不同值时视为需要核对的信息，前置提醒横幅并逐值展示，便于发现不一致。
 * - 正文按轻量 Markdown 渲染（加粗、有序/无序列表、段落），只生成 React 元素，绝不执行模型返回的 HTML。
 * - 每条值的引用仅来自该值自己的 citations（经校验的真实依据），点击即定位原文。
 */
export function ModuleMarkdown({
  items,
  onLocate,
  activeId,
}: {
  items: AnalysisField[];
  onLocate: (ref: Citation) => void;
  activeId?: string;
}) {
  const groups = useMemo(() => groupFields(items), [items]);
  const conflicts = useMemo(() => items.filter(needsReview), [items]);

  return (
    <div className="module-markdown">
      {conflicts.length > 0 && (
        <div role="note" className="module-conflict-banner">
          <strong>发现 {conflicts.length} 处需要核对的信息</strong>
          <ul>
            {conflicts.map((item) => (
              <li key={item.id}>
                {item.field}
                {item.values.length > 1 ? "：" + item.values.map((value) => value.value).join(" ／ ") : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {[...groups.entries()].map(([group, fields]) => (
        <section key={group} className="module-group">
          {group !== "未分类" && <h4 className="module-group-title">{group}</h4>}
          {fields.map((item) => (
            <article
              key={item.id}
              id={"report-item-" + item.id}
              data-report-item={item.id}
              className={"module-markdown-item " + (activeId === item.id ? "report-item-active" : "")}
            >
              <header className="module-markdown-heading">
                <h4>{renderInline(item.field)}</h4>
                {!!item.module_keys?.length && (
                  <span className="module-keys">{item.module_keys.length} 个专题</span>
                )}
              </header>
              <ul className="field-values">
                {item.values.map((value, index) => (
                  <li key={index} className="field-value">
                    <div className="module-markdown-body">{renderMarkdown(value.value)}</div>
                    <div className="report-citations">
                      {value.citations.map((ref, i) => (
                        <button
                          type="button"
                          key={ref.source_id + ":" + ref.element_id + ":" + i}
                          onClick={() => onLocate(ref)}
                        >
                          <span>{i + 1}</span>
                          <span className="truncate">{ref.file_name}</span>
                          <strong>第 {ref.page_no} 页 ↗</strong>
                        </button>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
              {!!item.note && <p className="field-note">{renderMarkdown(item.note)}</p>}
              {item.verification === "unsupported" && (
                <p className="mt-2 text-sm text-rose-700">引用尚不足以支持这条结论，请核对原文。</p>
              )}
              {item.verification === "unavailable" && (
                <p className="mt-2 text-sm text-slate-500">{item.note || "来源已不可用。"}</p>
              )}
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}

/** 分批提交顺序不等于展示顺序；组内稳定排序，同序字段保留提交先后。 */
function groupFields(items: AnalysisField[]): Map<string, AnalysisField[]> {
  const groups = new Map<string, AnalysisField[]>();
  for (const item of items) {
    const key = item.group?.trim() || "未分类";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  for (const fields of groups.values()) fields.sort((a, b) => a.sort_order - b.sort_order);
  return groups;
}

/** 一个字段出现多个不同值，或引用未获支持时，属于需要用户核对的信息。 */
function needsReview(item: AnalysisField): boolean {
  if (item.verification === "unsupported" || item.verification === "unavailable") return true;
  const distinct = new Set(item.values.map((value) => value.value.trim()));
  return distinct.size > 1;
}

/** 轻量 Markdown 块级渲染：段落、无序列表（-/•）、有序列表（1./1、），空行分段。 */
function renderMarkdown(text: string): ReactNode {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; entries: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const entries = list.entries.map((entry, i) => <li key={i}>{renderInline(entry)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{entries}</ol> : <ul key={blocks.length}>{entries}</ul>);
    list = null;
  };
  for (const line of text.split(/\n/)) {
    const bullet = line.match(/^\s*[-•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.、)]\s+(.*)$/);
    if (bullet) {
      if (!list || list.ordered) { flush(); list = { ordered: false, entries: [] }; }
      list.entries.push(bullet[1] ?? "");
    } else if (numbered) {
      if (!list || !list.ordered) { flush(); list = { ordered: true, entries: [] }; }
      list.entries.push(numbered[1] ?? "");
    } else {
      flush();
      if (line.trim()) blocks.push(<p key={blocks.length}>{renderInline(line)}</p>);
    }
  }
  flush();
  return blocks;
}

/** 行内渲染：只支持加粗，其余保持原文本；不解析任何 HTML。 */
function renderInline(text: string): ReactNode[] {
  if (!text.includes("**")) return [text];
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : <Fragment key={index}>{part}</Fragment>);
}
