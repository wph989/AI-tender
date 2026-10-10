"use client";

import { Fragment, useMemo, type ReactElement, type ReactNode } from "react";
import { Icon } from "@/components/Icon";
import type { AnalysisField, Citation, FieldValue } from "@/types/knowledge";

/**
 * 解析结果 Markdown 表格视图：一行一个字段，列为「字段 / 解析值」。
 * - 表格形态便于横向对照同组字段，也避免旧版卡片流把同一处引用铺成整屏。
 * - 定位图标跟在取值后面（不单独占一列）：图标紧贴它要证明的那个值，一眼能看出值得位置。
 *   同一个值里重复的同一处原文按“资料 + 元素 + 页 + 摘录”去重，只留一个图标。
 * - 每个值仍绑定自己的引用（经校验的真实依据），重复值提醒与未支持提示保持原样。
 * - 正文按轻量 Markdown 渲染（段落、列表、加粗），只生成 React 元素，绝不执行模型返回的 HTML。
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
          <table className="module-table">
            <thead>
              <tr>
                <th scope="col">字段</th>
                <th scope="col">解析值</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((item) => (
                <tr
                  key={item.id}
                  id={"report-item-" + item.id}
                  data-report-item={item.id}
                  className={activeId === item.id ? "report-item-active" : ""}
                >
                  <th scope="row">
                    <span className="module-field-name">{renderInline(item.field)}</span>
                    {/* 只在综合字段里标注跨专题来源；模块视图每行本来就属于同一专题。 */}
                    {(item.module_keys?.length ?? 0) > 1 && (
                      <span className="module-keys">{item.module_keys?.length} 个专题</span>
                    )}
                  </th>
                  <td>
                    <ul className="field-values">
                      {item.values.map((value, index) => (
                        // 沿用正文样式类：轻量 Markdown 的段落/列表间距对取值同样适用。
                        <li key={index} className="field-value module-markdown-body">
                          {renderMarkdown(
                            value.value,
                            <ValueLocates refs={valueCitations(value)} onLocate={onLocate} />,
                          )}
                        </li>
                      ))}
                    </ul>
                    {!!item.note && <p className="field-note">{renderMarkdown(item.note)}</p>}
                    {item.verification === "unsupported" && (
                      <p className="field-warning">引用尚不足以支持这条结论，请核对原文。</p>
                    )}
                    {item.verification === "unavailable" && (
                      <p className="field-note">{item.note || "来源已不可用。"}</p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

/** 取值后面紧跟的定位图标：没有引用时不渲染，避免出现点不开的空图标。 */
function ValueLocates({ refs, onLocate }: { refs: Citation[]; onLocate: (ref: Citation) => void }) {
  if (!refs.length) return null;
  return (
    <span className="value-locates">
      {refs.map((ref, index) => (
        <button
          type="button"
          key={ref.source_id + ":" + ref.element_id + ":" + index}
          title={locateTitle(ref)}
          aria-label={"定位：" + locateTitle(ref)}
          onClick={() => onLocate(ref)}
        >
          <Icon name="target" size={13} />
        </button>
      ))}
    </span>
  );
}

/**
 * 单个值自己的引用去重：按钮跟在值后面，重复的同一处原文在这个值里没有额外信息。
 */
function valueCitations(value: FieldValue): Citation[] {
  const seen = new Set<string>();
  const result: Citation[] = [];
  for (const ref of value.citations ?? []) {
    const key = [ref.source_id, ref.element_id, ref.page_no, ref.quote].join("\u0000");
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(ref);
  }
  return result;
}

function locateTitle(ref: Citation): string {
  const where = (ref.file_name ?? "原文") + (ref.page_no ? " 第 " + ref.page_no + " 页" : "");
  const quote = (ref.quote ?? "").replace(/\s+/g, " ").trim();
  return quote ? where + "：" + quote.slice(0, 42) : where;
}

/** 一个字段出现多个不同值，或引用未获支持时，属于需要用户核对的信息。 */
function needsReview(item: AnalysisField): boolean {
  if (item.verification === "unsupported" || item.verification === "unavailable") return true;
  const distinct = new Set(item.values.map((value) => value.value.trim()));
  return distinct.size > 1;
}

/**
 * 轻量 Markdown 块级渲染：段落、无序列表（-/•）、有序列表（1./1、），空行分段。
 * trailing 是取值末尾的定位图标：单段值直接接在同一行，列表等块结构接在最后一块之后。
 */
function renderMarkdown(text: string, trailing?: ReactNode): ReactNode {
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
  if (trailing) {
    const last = blocks[blocks.length - 1] as ReactElement<{ children?: ReactNode }> | undefined;
    if (last?.type === "p") {
      blocks[blocks.length - 1] = (
        <p key={last.key ?? undefined}>
          {last.props.children}
          {trailing}
        </p>
      );
    } else {
      blocks.push(<Fragment key={"locates-" + blocks.length}>{trailing}</Fragment>);
    }
  }
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
