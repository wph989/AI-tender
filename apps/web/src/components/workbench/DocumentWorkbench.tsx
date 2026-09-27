"use client";

/**
 * 项目工作台（本切片为单文档最小形态，见 docs/设计/06 第 1 / 2 节）。
 *
 * 数据来源是 public/samples 下的静态样本 + 静态 PDF：阶段 1 的验收标准就是
 * 「先用假结果数据跑通点击定位」（见 docs/工程/07）。接口落地后只需替换 lib/api/client.ts，
 * 本文件一行不用动——这正是把取数收进 client.ts 的原因。
 */

import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useState } from "react";

import { ResultPanel } from "@/components/results/ResultPanel";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";
import { Toolbar } from "@/components/workbench/Toolbar";
import { useEvidenceIndex } from "@/hooks/useEvidenceIndex";
import { useLocate } from "@/hooks/useLocate";
import { usePageRegistry } from "@/hooks/usePageRenderer";
import { loadSampleWorkbench, type WorkbenchData } from "@/lib/api/client";
import { destroyPdfDocument, loadPdfDocument } from "@/lib/pdf/document";
import { useViewerStore } from "@/lib/store/viewerStore";
import { toActiveEvidence, type EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireExtraction } from "@/types/workbench";

/** 共享空数组：加载完成前必须给 useEvidenceIndex 一个稳定引用，否则每渲染一次就重建索引 */
const EMPTY_EXTRACTIONS: readonly WireExtraction[] = [];

export function DocumentWorkbench() {
  const [data, setData] = useState<WorkbenchData | null>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const registry = usePageRegistry();
  const { locate } = useLocate(registry);
  const index = useEvidenceIndex(data?.extractions ?? EMPTY_EXTRACTIONS);

  const notice = useViewerStore((state) => state.notice);
  const setNotice = useViewerStore((state) => state.setNotice);

  useEffect(() => {
    let alive = true;
    loadSampleWorkbench()
      .then((loaded) => {
        if (alive) setData(loaded);
      })
      .catch((error: unknown) => {
        if (alive) setLoadError(error instanceof Error ? error.message : "样本数据加载失败");
      });
    return () => {
      alive = false;
    };
  }, []);

  // PDF 基座单独加载：文档加载失败时页面其余部分仍可浏览（结果面板照常显示），
  // 错误只落在原文区，不把整页变成错误页
  useEffect(() => {
    if (data === null) return;
    let alive = true;
    let loaded: PDFDocumentProxy | null = null;
    loadPdfDocument(data.pdfUrl)
      .then((document) => {
        if (!alive) {
          destroyPdfDocument(document);
          return;
        }
        loaded = document;
        setPdf(document);
      })
      .catch((error: unknown) => {
        if (alive) setLoadError(error instanceof Error ? error.message : "PDF 加载失败");
      });
    return () => {
      alive = false;
      if (loaded !== null) destroyPdfDocument(loaded);
    };
  }, [data]);

  const handleLocate = useCallback(
    (target: EvidenceTarget) => {
      void locate(toActiveEvidence(target));
    },
    [locate],
  );

  // 传给整棵原文视图的错误回调必须稳定：它进了 CanvasLayer 的 effect 依赖，
  // 每次渲染换一个新函数会导致 canvas 反复重渲染
  const handleViewerError = useCallback(
    (message: string) => {
      setNotice(message);
    },
    [setNotice],
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Toolbar pageCount={data?.pages.length ?? 0} />

      {notice !== null && (
        <div className="flex items-center gap-3 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          <span className="flex-1">{notice}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="rounded px-2 py-0.5 text-xs text-amber-700 hover:bg-amber-100"
          >
            关闭
          </button>
        </div>
      )}

      {loadError !== null ? (
        <div className="flex flex-1 items-center justify-center p-8 text-sm text-rose-700">
          {loadError}
        </div>
      ) : data === null || pdf === null ? (
        <div className="flex flex-1 items-center justify-center p-8 text-sm text-slate-500">
          正在加载样本文档…
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1">
            <DocumentViewer
              pdf={pdf}
              pages={data.pages}
              index={index}
              registry={registry}
              onError={handleViewerError}
            />
          </div>
          <ResultPanel extractions={data.extractions} index={index} onLocate={handleLocate} />
        </div>
      )}
    </div>
  );
}