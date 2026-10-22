"use client";

import type { PDFDocumentProxy } from "pdfjs-dist";
import { useEffect, useMemo, useRef, useState } from "react";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";
import { Toolbar } from "@/components/workbench/Toolbar";
import { useLocate } from "@/hooks/useLocate";
import { usePageRegistry } from "@/hooks/usePageRenderer";
import { knowledgeRequest } from "@/lib/api/knowledge";
import { toBbox } from "@/lib/api/wire";
import { destroyPdfDocument, loadPdfDocument } from "@/lib/pdf/document";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceIndex, EvidenceItem, EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { Citation } from "@/types/knowledge";
import type { WirePageMeta } from "@/types/workbench";

interface Props {
  selected: Citation | Pick<Citation, "version_id" | "file_name">;
  citations: Citation[];
  /** 当前点击事项在当前位置的原始摘录，不与其它事项的同位置引用混合。 */
  quotes?: string[];
  onReverse?: (ref: Citation) => void;
}

/** 复用同一 PDF.js、虚拟页和定位 Hook；父级用版本及批次作为 key 隔离旧定位。 */
export function CitationViewer({ selected, citations, quotes, onReverse }: Props) {
  // 默认预览只需要文件身份，不伪造引用、页码锚点或高亮区域。
  const citation = "source_id" in selected ? selected : null;
  const excerpts = quotes?.length ? quotes : citation ? [citation.quote] : [];
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<WirePageMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const lastLocated = useRef<Citation | null>(null);
  const registry = usePageRegistry();
  const { locate } = useLocate(registry);
  const notice = useViewerStore((state) => state.notice);
  const currentPage = useViewerStore((state) => state.currentPage);
  const refs = useMemo(() => {
    if (!citation) return [];
    // 多条结论可引用同一原文块；只画一次框和角标，避免重复标记干扰原文阅读。
    const blocks = new Map<number, Citation>();
    for (const ref of citations) {
      if (ref.source_id === citation.source_id && ref.version_id === citation.version_id && ref.parse_run_id === citation.parse_run_id) blocks.set(ref.element_id, ref);
    }
    blocks.set(citation.element_id, citation);
    return [...blocks.values()];
  }, [citations, citation]);
  const index = useMemo<EvidenceIndex>(() => {
    const byPage = new Map<number, EvidenceItem[]>();
    const byEvidence = new Map<number, EvidenceTarget[]>();
    refs.forEach((ref, i) => {
      const bbox = toBbox(ref.bbox);
      const target: EvidenceTarget = { evidenceId: i + 1, anchor: ref.anchor, pageNo: ref.page_no, bbox, label: ref.file_name, quote: ref.quote };
      byEvidence.set(i + 1, [target]);
      if (bbox) {
        const list = byPage.get(ref.page_no) ?? [];
        list.push({ ...target, bbox, badge: list.length + 1 });
        byPage.set(ref.page_no, list);
      }
    });
    return { byPage, byEvidence };
  }, [refs]);

  useEffect(() => {
    useViewerStore.setState({ activeEvidence: null, currentPage: 1, jumpRequest: null, notice: null });
    let alive = true;
    let document: PDFDocumentProxy | null = null;
    const abort = new AbortController();
    knowledgeRequest<{ pages: WirePageMeta[] }>("/versions/" + selected.version_id + "/pages", "GET", undefined, abort.signal)
      .then((data) => { if (alive) setPages(data.pages); }).catch((e: Error) => { if (alive) setError(e.message); });
    loadPdfDocument("/api/v1/versions/" + selected.version_id + "/file").then((loaded) => {
      if (!alive) { destroyPdfDocument(loaded); return; }
      document = loaded; setPdf(loaded);
    }).catch((e: Error) => { if (alive) setError(e.message); });
    return () => { alive = false; abort.abort(); if (document) destroyPdfDocument(document); };
  }, [selected.version_id]);

  useEffect(() => {
    if (!citation || !pdf || !pages.length) return;
    // 报告轮询只更新角标集合，不应把正在阅读的用户重新滚回旧引用。
    if (lastLocated.current === citation) return;
    lastLocated.current = citation;
    void locate({ evidenceId: Math.max(1, refs.findIndex((r) => r.element_id === citation.element_id && r.quote === citation.quote) + 1),
      anchor: citation.anchor, pageNo: citation.page_no, bbox: toBbox(citation.bbox), label: citation.file_name });
  }, [pdf, pages, citation, locate, refs]);

  return <section className="citation-viewer" aria-label={citation ? "引用原文" : "文档预览"}>
    <div className="citation-heading"><strong className="truncate">{selected.file_name}</strong><span>第 {currentPage} 页</span></div>
    <Toolbar pageCount={pages.length} />
    {(error || notice) && <p role="status" className="notice m-2">{error ?? notice}</p>}
    <div className="min-h-0 flex-1">{pdf && pages.length ? <DocumentViewer pdf={pdf} pages={pages} index={index} registry={registry} onError={setError}
      onLocate={(item) => { const ref = refs[item.evidenceId - 1]; if (ref) onReverse?.(ref); }} />
      : <p className="p-8 text-slate-500">正在打开文档…</p>}</div>
    {/* 多摘录可点击或触屏展开；每段仍是原始引文，不拼接后冒充一条证据。 */}
    {citation && (excerpts.length > 1
      ? <details key={excerpts.join("\u0000")} className="citation-excerpt">
          <summary>查看本事项的 {excerpts.length} 条原文摘录</summary>
          {excerpts.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}
        </details>
      : <blockquote className="citation-excerpt">{excerpts[0]}</blockquote>)}
  </section>;
}
