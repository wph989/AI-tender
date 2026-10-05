"use client";
import type { AnalysisItem, Citation } from "@/types/knowledge";

const KINDS = { fact: "原文事实", judgment: "综合判断", suggestion: "建议", conflict: "材料冲突", insufficient: "证据不足" };

/** 每行独立绑定引用，不解析生成文本中的页码，也不执行模型返回的 HTML。 */
export function ReportItems({ items, onLocate, activeId }: { items: AnalysisItem[]; onLocate: (ref: Citation) => void; activeId?: string }) {
  return <div className="report-items">{items.map((item) => <article key={item.id} id={"report-item-" + item.id} data-report-item={item.id}
    className={"report-item " + (activeId === item.id ? "report-item-active" : "")}>
    <div className="mb-2 flex items-start gap-2"><span className={"report-kind report-kind-" + item.kind}>{KINDS[item.kind]}</span><h4 className="font-semibold">{item.title}</h4></div>
    <p className="whitespace-pre-wrap leading-7">{item.text}</p>
    {item.presentation === "table" && Object.keys(item.cells).length > 0 && <div className="overflow-x-auto mt-3"><table className="report-table"><thead><tr>{Object.keys(item.cells).map((key) => <th key={key}>{key}</th>)}</tr></thead><tbody><tr>{Object.entries(item.cells).map(([key, value]) => <td key={key}>{value}</td>)}</tr></tbody></table></div>}
    {item.verification === "unsupported" && <p className="mt-2 text-sm text-rose-700">引用尚不足以支持这条结论，请核对原文。</p>}
    <div className="report-citations">{item.citations.map((ref, i) => <button type="button" key={ref.source_id + ":" + ref.element_id + ":" + i} onClick={() => onLocate(ref)}>
      <span>{i + 1}</span><span className="truncate">{ref.file_name}</span><strong>第 {ref.page_no} 页 ↗</strong>
    </button>)}</div>
  </article>)}</div>;
}
