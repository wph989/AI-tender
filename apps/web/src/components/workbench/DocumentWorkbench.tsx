"use client";

import { Button } from "antd";
import Link from "next/link";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useState } from "react";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";
import { OutlineNav } from "@/components/workbench/OutlineNav";
import { Toolbar } from "@/components/workbench/Toolbar";
import { useLocate } from "@/hooks/useLocate";
import { usePageRegistry } from "@/hooks/usePageRenderer";
import { loadOutline, loadWorkbench, type WorkbenchData } from "@/lib/api/client";
import { toBbox } from "@/lib/api/wire";
import { destroyPdfDocument, loadPdfDocument } from "@/lib/pdf/document";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceIndex } from "@/lib/viewer/evidenceIndex";
import type { WireOutlineItem } from "@/types/workbench";

const EMPTY_INDEX: EvidenceIndex = { byPage: new Map(), byEvidence: new Map() };

/** 文档预览只负责原文和章节；专题成果统一在项目分析页维护。 */
export function DocumentWorkbench({
  versionId,
  refreshToken,
}: {
  versionId: number;
  refreshToken?: string;
  onSettled?: () => void;
}) {
  const [data, setData] = useState<WorkbenchData | null>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [outline, setOutline] = useState<WireOutlineItem[]>([]);
  const [collapsed, setCollapsed] = useState(true);
  const registry = usePageRegistry();
  const { locate } = useLocate(registry);
  const currentPage = useViewerStore((state) => state.currentPage);
  const notice = useViewerStore((state) => state.notice);
  const requestJump = useViewerStore((state) => state.requestJump);
  const setNotice = useViewerStore((state) => state.setNotice);

  useEffect(() => {
    // 章节锚点仅在版本内唯一，换文档必须清除上一次的页码与高亮。
    useViewerStore.setState({ activeEvidence: null, currentPage: 1, jumpRequest: null, notice: null });
  }, [versionId]);

  useEffect(() => {
    let alive = true;
    setError(null);
    void Promise.all([loadWorkbench(versionId), loadOutline(versionId)]).then(([loaded, headings]) => {
      if (alive) { setData(loaded); setOutline(headings); }
    }).catch((caught: unknown) => {
      if (alive) setError(caught instanceof Error ? caught.message : "文档加载失败");
    });
    return () => { alive = false; };
  }, [versionId, refreshToken, attempt]);

  const pdfUrl = data?.pdfUrl;
  useEffect(() => {
    if (!pdfUrl) return;
    let alive = true;
    let loaded: PDFDocumentProxy | null = null;
    setPdf(null);
    void loadPdfDocument(pdfUrl).then((document) => {
      if (!alive) { destroyPdfDocument(document); return; }
      loaded = document;
      setPdf(document);
    }).catch((caught: unknown) => {
      if (alive) setError(caught instanceof Error ? caught.message : "PDF 加载失败");
    });
    return () => { alive = false; if (loaded) destroyPdfDocument(loaded); };
  }, [pdfUrl, attempt]);

  const selectHeading = useCallback((item: WireOutlineItem) => {
    const block = data?.blocksByPage[String(item.page_no)]?.find((row) => row.anchor === item.anchor);
    const bbox = block ? toBbox(block.bbox) : null;
    if (!bbox) { requestJump(item.page_no); return; }
    void locate({ evidenceId: -1, anchor: item.anchor, pageNo: item.page_no, bbox, label: item.text });
  }, [data, locate, requestJump]);

  return (
    <div className="workbench">
      <Toolbar pageCount={data?.pages.length ?? 0} />
      {data?.projectId != null && (
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-2 text-sm">
          <span className="text-slate-500">
            {data.parseError ?? (
              ["completed", "partial"].includes(data.parseStatus ?? "")
                ? "原文已就绪，可在项目分析中汇总各专题要求。"
                : "原文解析尚未完成，可到文件管理查看进度。"
            )}
          </span>
          <Link href={"/projects/" + data.projectId} className="text-sky-700">查看项目分析</Link>
          <Link href={"/projects/" + data.projectId + "/files"} className="text-sky-700">文件管理</Link>
        </div>
      )}
      {notice && <p role="status" className="notice m-2">{notice}</p>}
      {error ? (
        <div role="alert" className="p-6">
          <p>{error}</p>
          <Button onClick={() => setAttempt((value) => value + 1)}>重新加载</Button>
        </div>
      ) : !data || !pdf ? (
        <p className="p-6 text-slate-500">正在加载文档原文…</p>
      ) : (
        <div className="flex min-h-0 flex-1">
          <OutlineNav items={outline} currentPage={currentPage} collapsed={collapsed}
            onToggle={() => setCollapsed((value) => !value)} onSelect={selectHeading} />
          <div className="min-w-0 flex-1">
            <DocumentViewer pdf={pdf} pages={data.pages} index={EMPTY_INDEX}
              registry={registry} onError={setNotice} onLocate={() => undefined} />
          </div>
        </div>
      )}
    </div>
  );
}
