"use client";

import { useMemo, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Icon } from "@/components/Icon";
import type { AnalysisField, Citation, FieldValue } from "@/types/knowledge";

/**
 * 解析结果 Markdown 表格视图：一行一个字段，列为「字段 / 解析值」。
 * - 表格形态便于横向对照同组字段，也避免旧版卡片流把同一处引用铺成整屏。
 * - 定位图标跟在取值后面（不单独占一列）：图标紧贴它要证明的那个值，一眼能看出值得位置。
 *   同一个值里重复的同一处原文按“资料 + 元素 + 页 + 摘录”去重，只留一个图标。
 * - 每个值仍绑定自己的引用（经校验的真实依据），重复值提醒与未支持提示保持原样。
 * - 正文由 react-markdown 与 GFM 插件渲染，支持标准列表和表格，忽略模型返回的 HTML。
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
                {item.values.length > 1
                  ? "：" + item.values.map((value) => value.value).join(" ／ ")
                  : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {[...groups.entries()].map(([group, fields]) => (
        <section key={group} className="module-group">
          {group !== "未分类" && (
            <h4 className="module-group-title">{group}</h4>
          )}
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
                    <span className="module-field-name">
                      {renderInline(item.field)}
                    </span>
                    {/* 只在综合字段里标注跨专题来源；模块视图每行本来就属于同一专题。 */}
                    {(item.module_keys?.length ?? 0) > 1 && (
                      <span className="module-keys">
                        {item.module_keys?.length} 个专题
                      </span>
                    )}
                  </th>
                  <td>
                    <ul className="field-values">
                      {item.values.map((value, index) => (
                        // 沿用正文样式类：轻量 Markdown 的段落/列表间距对取值同样适用。
                        <li
                          key={index}
                          className="field-value module-markdown-body"
                        >
                          {renderMarkdown(
                            value.value,
                            <ValueLocates
                              refs={valueCitations(value)}
                              onLocate={onLocate}
                            />,
                          )}
                        </li>
                      ))}
                    </ul>
                    {!!item.note && (
                      <div className="field-note">
                        {renderMarkdown(item.note)}
                      </div>
                    )}
                    {item.verification === "unsupported" && (
                      <p className="field-warning">
                        引用尚不足以支持这条结论，请核对原文。
                      </p>
                    )}
                    {item.verification === "unavailable" && (
                      <p className="field-note">
                        {item.note || "来源已不可用。"}
                      </p>
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
  for (const fields of groups.values())
    fields.sort((a, b) => a.sort_order - b.sort_order);
  return groups;
}

/** 取值后面紧跟的定位图标：没有引用时不渲染，避免出现点不开的空图标。 */
function ValueLocates({
  refs,
  onLocate,
}: {
  refs: Citation[];
  onLocate: (ref: Citation) => void;
}) {
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
    const key = [ref.source_id, ref.element_id, ref.page_no, ref.quote].join(
      "\u0000",
    );
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(ref);
  }
  return result;
}

function locateTitle(ref: Citation): string {
  const where =
    (ref.file_name ?? "原文") +
    (ref.page_no ? " 第 " + ref.page_no + " 页" : "");
  const quote = (ref.quote ?? "").replace(/\s+/g, " ").trim();
  return quote ? where + "：" + quote.slice(0, 42) : where;
}

/** 一个字段出现多个不同值，或引用未获支持时，属于需要用户核对的信息。 */
function needsReview(item: AnalysisField): boolean {
  if (
    item.verification === "unsupported" ||
    item.verification === "unavailable"
  )
    return true;
  const distinct = new Set(item.values.map((value) => value.value.trim()));
  return distinct.size > 1;
}

/** 只扩展值末尾的业务定位入口，Markdown 语法由成熟解析器处理。 */
interface MarkdownNode {
  type: string;
  children?: MarkdownNode[];
  data?: { hName: string; hProperties?: Record<string, string> };
}
function appendCitations() {
  return (tree: MarkdownNode) => {
    const marker: MarkdownNode = {
      type: "citationAnchor",
      data: { hName: "span", hProperties: { className: "citation-anchor" } },
    };
    const last = tree.children?.at(-1);
    // 普通取值的图标接在最后一段行内，列表/表格则在最后一个块之后，保持既有定位语义。
    if (last?.type === "paragraph") last.children?.push(marker);
    else tree.children?.push({ type: "paragraph", children: [marker] });
  };
}

function renderMarkdown(text: string, trailing?: ReactNode): ReactNode {
  return (
    <Markdown
      skipHtml
      remarkPlugins={trailing ? [remarkGfm, appendCitations] : [remarkGfm]}
      components={{
        span: ({ className, children }) =>
          className === "citation-anchor" ? (
            trailing
          ) : (
            <span className={className}>{children}</span>
          ),
        table: ({ children }) => (
          <div className="overflow-x-auto">
            <table>{children}</table>
          </div>
        ),
        // 模型返回的图片只展示说明，避免报告正文自行向第三方发起图片请求。
        img: ({ alt }) => <span>{alt}</span>,
      }}
    >
      {text}
    </Markdown>
  );
}

function renderInline(text: string): ReactNode {
  return (
    <Markdown
      skipHtml
      components={{ p: "span", img: ({ alt }) => <span>{alt}</span> }}
    >
      {text}
    </Markdown>
  );
}
