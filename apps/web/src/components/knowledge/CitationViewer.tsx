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
  selected: Citation;
  citations: Citation[];
  onReverse?: (ref: Citation) => void;
}

/** 复用同一 PDF.js、虚拟页和定位 Hook；父级用版本及批次作为 key 隔离旧定位。 */
export function CitationViewer({ selected, citations, onReverse }: Props) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<WirePageMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const lastLocated = useRef<Citation | null>(null);
  const registry = usePageRegistry();
  const { locate } = useLocate(registry);
  const notice = useViewerStore((state) => state.notice);
  const refs = useMemo(() => {
    // 多条结论可引用同一原文块；画一次框即可，重复叠色会遮住正文。
    const blocks = new Map<number, Citation>();
    for (const ref of citations) {
      if (ref.source_id === selected.source_id && ref.version_id === selected.version_id && ref.parse_run_id === selected.parse_run_id) blocks.set(ref.element_id, ref);
    }
    blocks.set(selected.element_id, selected);
    return [...blocks.values()];
  }, [citations, selected]);
  const index = useMemo<EvidenceIndex>(() => {
    const byPage = new Map<number, EvidenceItem[]>();
    const byExtraction = new Map<number, EvidenceTarget[]>();
    refs.forEach((ref, i) => {
      const bbox = toBbox(ref.bbox);
      const target: EvidenceTarget = { extractionId: i + 1, anchor: ref.anchor, pageNo: ref.page_no, bbox, fieldKey: "citation", label: ref.file_name, quote: ref.quote };
      byExtraction.set(i + 1, [target]);
      if (bbox) {
        const list = byPage.get(ref.page_no) ?? [];
        list.push({ ...target, bbox, badge: list.length + 1 });
        byPage.set(ref.page_no, list);
      }
    });
    return { byPage, byExtraction };
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
    if (!pdf || !pages.length) return;
    // 报告轮询只更新角标集合，不应把正在阅读的用户重新滚回旧引用。
    if (lastLocated.current === selected) return;
    lastLocated.current = selected;
    void locate({ extractionId: Math.max(1, refs.findIndex((r) => r.element_id === selected.element_id && r.quote === selected.quote) + 1),
      anchor: selected.anchor, pageNo: selected.page_no, bbox: toBbox(selected.bbox), label: selected.file_name });
  }, [pdf, pages, selected, locate, refs]);

  return <section className="citation-viewer" aria-label="引用原文">
    <div className="citation-heading"><strong className="truncate">{selected.file_name}</strong><span>第 {selected.page_no} 页</span></div>
    <Toolbar pageCount={pages.length} projectId={null} onNotice={setError} showExport={false} />
    {(error || notice) && <p role="status" className="notice m-2">{error ?? notice}</p>}
    <div className="min-h-0 flex-1">{pdf && pages.length ? <DocumentViewer pdf={pdf} pages={pages} index={index} registry={registry} onError={setError}
      onLocate={(item) => { const ref = refs[item.extractionId - 1]; if (ref) onReverse?.(ref); }} />
      : <p className="p-8 text-slate-500">正在打开引用原文…</p>}</div>
    <blockquote className="citation-excerpt">{selected.quote}</blockquote>
  </section>;
}
