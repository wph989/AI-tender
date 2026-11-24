"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { EvidenceReferences as ValueLocates } from "./EvidenceReferences";
import { scopeLabel } from "@/lib/analysis/scope";
import { keyValueRows, unpairedFields } from "@/lib/analysis/presentation";
import { presentCitations } from "@/lib/analysis/citations";
import type { AnalysisField, BusinessRecord, Citation, FieldValue } from "@/types/knowledge";

/**
 * 专题使用 Skill 定义的分类、列名和树结构，问答展示逐项取值，共用 Markdown 与引用渲染。
 * - 定位与综合正文独立绑定，让归纳后的要求仍可回查完整原文。
 * - 专题正文按单元绑定来源，同一事项内的位置只在首次出现的正文后展示，全部摘录保留在提示中。
 * - 每个值仍绑定自己的引用（经校验的真实依据），重复值提醒与未支持提示保持原样。
 * - 正文由 react-markdown 与 GFM 插件渲染，支持标准列表和表格，忽略模型返回的 HTML。
 */
export function ModuleMarkdown({
  items,
  onLocate,
  activeId,
  relatedItems,
  resolvedRelations = [],
  filtered = false,
  locationRevision = 0,
  onRevealItem,
}: {
  items: AnalysisField[];
  onLocate: (ref: Citation, itemId?: string) => void;
  activeId?: string;
  relatedItems?: AnalysisField[];
  resolvedRelations?: BusinessRecord[];
  filtered?: boolean;
  locationRevision?: number;
  onRevealItem?: (id: string) => void;
}) {
  const groups = useMemo(() => groupFields(items), [items]);
  const conflicts = useMemo(() => items.filter(needsReview), [items]);

  if (items.some((item) => item.output)) {
    return <StructuredModule items={items} onLocate={onLocate} activeId={activeId}
      relatedItems={relatedItems ?? items} resolvedRelations={resolvedRelations}
      filtered={filtered} locationRevision={locationRevision} onRevealItem={onRevealItem} />;
  }

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
                              onLocate={(ref) => onLocate(ref, item.id)}
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

/** 身份、适用范围和依据共用一套展示；具体内容按字段语义选择阅读结构。 */
function StructuredModule({ items, onLocate, activeId, relatedItems, resolvedRelations, filtered, locationRevision, onRevealItem }: {
  items: AnalysisField[];
  onLocate: (ref: Citation, itemId?: string) => void;
  activeId?: string;
  relatedItems: AnalysisField[];
  resolvedRelations: BusinessRecord[];
  filtered: boolean;
  locationRevision: number;
  onRevealItem?: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  // 预先按整项分配入口，避免各列独立去重，也避免渲染过程消耗共享 Set 导致重渲染丢入口。
  const citations = useMemo(() => new Map(items.map((item) => [item.id, presentCitations(item)])), [items]);
  const nodes = items.filter((item) => item.output?.layout === "tree");
  const nodeKeys = new Set(nodes.map((item) => item.output!.key));
  const groups = groupFields(items.filter((item) => item.output?.layout !== "tree"));
  useEffect(() => {
    // 父子都命中时也要展开；contextOnly 只表示计数身份，不能代表是否正在筛选。
    const opened: Record<string, boolean> = Object.fromEntries(filtered
      ? items.filter((item) => item.output?.layout === "tree").map((item) => [item.id, true]) : []);
    const active = items.find((item) => item.id === activeId);
    if (active) opened[active.id] = true;
    let parent = active?.output?.parent_key;
    const visited = new Set<string>();
    while (parent && !visited.has(parent)) {
      visited.add(parent);
      const item = items.find((candidate) => candidate.output?.key === parent);
      if (!item) break;
      opened[item.id] = true;
      parent = item.output?.parent_key;
    }
    if (Object.keys(opened).length) setExpanded((previous) => ({ ...previous, ...opened }));
  }, [activeId, items, filtered, locationRevision]);
  const identity = (item: AnalysisField) => ({
    id: "report-item-" + item.id, "data-report-item": item.id,
    className: "result-record" + (activeId === item.id ? " report-item-active" : ""),
  });
  const content = (value: string | string[] | undefined, item?: AnalysisField, column?: string, offset = 0): ReactNode => {
    const render = (line: string, index: number) => {
      // KV 数组拆成表格行后仍使用原内容序号，不能让各行都取到第一条引用。
      const refs = item && column ? citations.get(item.id)?.content[column]?.[index + offset] : undefined;
      return renderMarkdown(line.replace(/<br\s*\/?>/gi, "\n\n"), refs?.length
        ? <ValueLocates inline refs={refs} onLocate={(ref) => onLocate(ref, item?.id)} /> : undefined);
    };
    return Array.isArray(value)
      ? <ul className="result-points">{value.map((line, index) => <li key={index}>{render(line, index)}</li>)}</ul>
      : value ? render(value, 0) : null;
  };
  const references = (item: AnalysisField) => {
    const extra = citations.get(item.id)?.extra ?? [];
    if (!extra.length) return null;
    if (!item.output?.citations) return <ValueLocates refs={extra} onLocate={(ref) => onLocate(ref, item.id)} />;
    return <p className="record-extra-evidence" role="group" aria-label="补充依据">补充依据
      <ValueLocates inline refs={extra} onLocate={(ref) => onLocate(ref, item.id)} />
    </p>;
  };
  const scope = (item: AnalysisField) => <span className="result-scope"
    data-unknown={item.record?.scope.kind === "unknown" || undefined}>
    {item.record ? "适用范围：" + scopeLabel(item.record.scope) : item.note}
    {item.contextOnly && " · 上级材料，仅供定位"}
  </span>;
  const relationLinks = (item: AnalysisField) => {
    const record = item.record;
    if (!record) return null;
    // 原始 key 会复用，端点内容或范围变化后关系可能失效；只用快照确认的身份连接。
    const relations = resolvedRelations.filter((relation) => relation.id === item.id
      || relation.object_id === item.id || relation.subject_id === item.id);
    if (record.kind === "relation" && !relations.length) return <p className="result-relations">
      关系端点或适用范围尚未确认，请结合原文及待核对事项核实。
    </p>;
    const links = relations.flatMap((relation) => {
      const endpoints = relatedItems.filter((candidate) => candidate.record?.kind !== "relation"
        && [relation.subject_id, relation.object_id].includes(candidate.id));
      return endpoints.filter((endpoint) => endpoint.id !== item.id).map((endpoint) => ({
        id: endpoint.id, title: endpoint.field,
        label: relation.predicate === "conflicts" ? "冲突条款" : relation.predicate === "supersedes"
          ? (endpoint.id === relation.subject_id
            ? "修订条款" : "原条款") : "关联条款",
      }));
    });
    if (!links.length && !record.superseded_in?.length && !record.conflicts_in?.length) return null;
    return <div className="result-relations">
      {Boolean(record.superseded_in?.length) && <span>部分适用范围已有修订</span>}
      {Boolean(record.conflicts_in?.length) && <span>存在待核对冲突</span>}
      {[...new Map(links.map((link) => [link.id, link])).values()].map((link) =>
        <button type="button" key={link.id} onClick={() => onRevealItem?.(link.id)}>
          {link.label}：{link.title}
        </button>)}
    </div>;
  };
  const heading = (item: AnalysisField) => <header className="result-record-heading">
    <div><h5>{renderInline(item.field)}</h5>{scope(item)}</div>
  </header>;
  const fields = (item: AnalysisField) => {
    const output = item.output;
    if (!output) return <p>{item.note || "来源已不可用，请更新分析。"}</p>;
    return <dl className="result-properties">{output.columns.filter((column) => column in output.content
      && column !== "满分分值").map((column) => <div key={column}>
      {column !== "背景" && <dt>{column}</dt>}
      <dd className="module-markdown-body">{content(output.content[column], item, column)}</dd>
    </div>)}</dl>;
  };
  const tree = (parent: string | null, path = new Set<string>()): ReactNode => <ul className="module-outline">
    {nodes.filter((item) => !path.has(item.output!.key) && (parent === null
      ? !item.output!.parent_key || !nodeKeys.has(item.output!.parent_key)
      : item.output!.parent_key === parent)).map((item) => <li key={item.id} {...identity(item)}>
      <details open={expanded[item.id] ?? parent === null}
        onToggle={(event) => {
          const open = event.currentTarget.open;
          setExpanded((old) => old[item.id] === open ? old : { ...old, [item.id]: open });
        }}>
        <summary><strong>{renderInline(item.field)}</strong>{scope(item)}</summary>
        <div className="module-markdown-body">{fields(item)}</div>
        {relationLinks(item)}{references(item)}
        {tree(item.output!.key, new Set([...path, item.output!.key]))}
      </details>
    </li>)}
  </ul>;
  return <div className="module-markdown">
    {!!nodes.length && <><div className="outline-actions">
      <button type="button" onClick={() => setExpanded(Object.fromEntries(nodes.map((item) => [item.id, true])))}>展开全部材料</button>
      <button type="button" onClick={() => setExpanded(Object.fromEntries(nodes.map((item) => [item.id, false])))}>收起全部材料</button>
    </div>{tree(null)}</>}
    {[...groups.entries()].map(([name, rows]) => {
      const output = rows.find((item) => item.output)?.output;
      const keyValue = output?.columns.length === 2 && output.columns[0] === "字段" && output.columns[1] === "内容";
      // 同组事项统一用表格比较，列名和内容仍来自冻结声明，长列表保留在单元格内。
      return <section key={name} className="module-group" data-result-group={name}>
        {name !== "未分类" && <h4 className="module-group-title">{name}</h4>}
        {keyValue ? <table className="module-table module-kv-table" aria-label={name}>
          <thead><tr><th scope="col">字段</th><th scope="col">内容</th></tr></thead>
          {rows.map((item) => {
            const pairs = keyValueRows(item);
            // 一条记录可含多对 KV，用 tbody 保留唯一事项身份，逐行显示时不制造重复锚点。
            return <tbody key={item.id} {...identity(item)}>{pairs.map((pair, index) => <tr key={index}>
              <th scope="row">{renderInline(pair.key)}</th>
              <td><div className="result-kv-value module-markdown-body">
                {content(pair.value, item, "内容", pair.contentIndex) || <span className="text-slate-400">未提供内容</span>}
              </div>
                {index === pairs.length - 1 && <div className="result-kv-context">
                  {scope(item)}{relationLinks(item)}{references(item)}
                  {unpairedFields(item) && <p className="record-attention">字段与内容数量不一致，请核对缺失项后重新解析。</p>}
                </div>}
              </td>
            </tr>)}</tbody>;
          })}
        </table> : output ? <div className="overflow-x-auto"><table className="module-table module-structured-table" aria-label={name}>
          <thead><tr>{output.columns.map((column) => <th scope="col" key={column}>{column}</th>)}</tr></thead>
          <tbody>{rows.map((item) => <tr key={item.id} {...identity(item)}>
            {output.columns.map((column, index) => <td key={column} data-label={column} className="module-markdown-body">
              {/* 标题来源列已经包含事项名称；未声明标题列时也避免逐字重复。 */}
              {index === 0 && !output.title_column && item.field !== [item.output?.content[column]].flat().join("；")
                && <h5>{renderInline(item.field)}</h5>}
              {/* 分值只在所属列展示，避免标题与单元格重复绘制同一定位入口。 */}
              <div className={column === "满分分值" ? "result-score" : undefined}>
                {content(item.output?.content[column], item, column) || <span className="text-slate-400">本项未提供</span>}
              </div>
              {column === (output.title_column ?? output.columns[0]) && <>{scope(item)}{relationLinks(item)}</>}
              {index === output.columns.length - 1 && references(item)}
            </td>)}
          </tr>)}</tbody>
        </table></div> : <div className="module-result-list">{rows.map((item) => <article key={item.id} {...identity(item)}>
          {heading(item)}{fields(item)}{relationLinks(item)}{references(item)}
        </article>)}</div>}
      </section>;
    })}
  </div>;
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
  // 项目概况先交代项目本身，再展示参与单位；不依赖模型分批提交的先后。
  if (items.some((item) => item.record?.module_key === "project_basic_info_parsing")) {
    const order = ["项目基本信息", "分标信息", "甲方信息", "代理信息"];
    const rank = (name: string) => order.includes(name) ? order.indexOf(name) : order.length;
    return new Map([...groups].sort(([a], [b]) => rank(a) - rank(b)));
  }
  return groups;
}

/** 摘录参与身份比较，不能把同一原文块的其它句子误认为已有定位。 */
function citationKey(ref: Citation): string {
  return [ref.source_id, ref.version_id, ref.parse_run_id, ref.element_id, ref.page_no, ref.quote].join("\u0000");
}

/** 单个值自己的引用去重：重复的同一处原文在这个值里没有额外信息。 */
function valueCitations(value: FieldValue): Citation[] {
  const seen = new Set<string>();
  const result: Citation[] = [];
  for (const ref of value.citations ?? []) {
    const key = citationKey(ref);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(ref);
  }
  return result;
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
