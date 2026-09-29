"use client";

import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useState } from "react";

import { ResultPanel } from "@/components/results/ResultPanel";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";
import { Toolbar } from "@/components/workbench/Toolbar";
import { useEvidenceIndex } from "@/hooks/useEvidenceIndex";
import { useLocate } from "@/hooks/useLocate";
import { usePageRegistry } from "@/hooks/usePageRenderer";
import {
  loadWorkbenchForCurrentPage,
  loadAttempts,
  loadFieldStats,
  rerunExtraction,
  submitReview,
  waitForJob,
  type ReviewInput,
  type WorkbenchData,
} from "@/lib/api/client";
import { destroyPdfDocument, loadPdfDocument } from "@/lib/pdf/document";
import { rerunModeByField, type RerunButtonMode } from "@/lib/results/rerun";
import { useViewerStore } from "@/lib/store/viewerStore";
import { toActiveEvidence, type EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireExtraction } from "@/types/workbench";

const EMPTY_EXTRACTIONS: readonly WireExtraction[] = [];

export function DocumentWorkbench() {
  const [data, setData] = useState<WorkbenchData | null>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyExtractionId, setBusyExtractionId] = useState<number | null>(null);
  const [rerunModes, setRerunModes] = useState<Record<string, RerunButtonMode>>({});

  const registry = usePageRegistry();
  const { locate } = useLocate(registry);
  const index = useEvidenceIndex(data?.extractions ?? EMPTY_EXTRACTIONS);

  const notice = useViewerStore((state) => state.notice);
  const setNotice = useViewerStore((state) => state.setNotice);

  // 统计是旁路：取不到就回落"全部显示重跑按钮"，不能让它挡住结果面板。
  const refreshStats = useCallback(async () => {
    try {
      setRerunModes(rerunModeByField(await loadFieldStats()));
    } catch {
      setRerunModes({});
    }
  }, []);

  const refreshWorkbench = useCallback(async () => {
    const loaded = await loadWorkbenchForCurrentPage();
    setData(loaded);
    setLoadError(null);
    void refreshStats();
    return loaded;
  }, [refreshStats]);

  useEffect(() => {
    let alive = true;
    refreshWorkbench()
      .then((loaded) => {
        if (alive) setData(loaded);
      })
      .catch((error: unknown) => {
        if (alive) setLoadError(error instanceof Error ? error.message : "文档数据加载失败");
      });
    return () => {
      alive = false;
    };
  }, [refreshWorkbench]);

  // PDF 基座单独加载：原文区失败时，结果面板仍能呈现可读的接口错误。
  const pdfUrl = data?.pdfUrl;
  useEffect(() => {
    if (pdfUrl === undefined) return;
    let alive = true;
    let loaded: PDFDocumentProxy | null = null;
    loadPdfDocument(pdfUrl)
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
  }, [pdfUrl]);

  const handleLocate = useCallback(
    (target: EvidenceTarget) => {
      void locate(toActiveEvidence(target));
    },
    [locate],
  );

  const handleViewerError = useCallback(
    (message: string) => {
      setNotice(message);
    },
    [setNotice],
  );

  const errorMessage = (error: unknown, fallback: string): string =>
    error instanceof Error ? error.message : fallback;

  const handleReview = useCallback(
    async (extraction: WireExtraction, input: ReviewInput): Promise<boolean> => {
      setBusyExtractionId(extraction.id);
      setNotice(null);
      try {
        await submitReview(extraction.instance_id, input);
        await refreshWorkbench();
        return true;
      } catch (error: unknown) {
        setNotice(errorMessage(error, "复核提交失败"));
        return false;
      } finally {
        setBusyExtractionId(null);
      }
    },
    [refreshWorkbench, setNotice],
  );

  const handleRerun = useCallback(
    async (extraction: WireExtraction, hint: string | null): Promise<boolean> => {
      setBusyExtractionId(extraction.id);
      setNotice(null);
      try {
        const queued = await rerunExtraction(extraction.id, hint);
        setNotice("字段重跑已提交，正在等待结果…");
        const job = await waitForJob(queued.job_id);
        if (job.status === "failed" || job.status === "canceled") {
          throw new Error(job.error_message ?? "字段重跑失败");
        }
        await refreshWorkbench();
        setNotice(null);
        return true;
      } catch (error: unknown) {
        setNotice(errorMessage(error, "字段重跑失败"));
        return false;
      } finally {
        setBusyExtractionId(null);
      }
    },
    [refreshWorkbench, setNotice],
  );

  // 批量确认逐条提交（后端是一次一条的复核接口），失败计数而不是中断：
  // 中途停下会让用户不知道到底确认了哪些，重刷一次就能看到真实状态。
  const handleBatchConfirm = useCallback(
    async (items: readonly WireExtraction[]): Promise<void> => {
      setNotice(`正在批量确认 ${items.length} 项…`);
      let failed = 0;
      for (const item of items) {
        try {
          await submitReview(item.instance_id, {
            attempt_id: item.id,
            action: "confirm",
            review_mode: "batch",
          });
        } catch {
          failed += 1;
        }
      }
      await refreshWorkbench();
      setNotice(failed > 0 ? `批量确认完成，${failed} 项失败，请重试` : null);
    },
    [refreshWorkbench, setNotice],
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Toolbar
        pageCount={data?.pages.length ?? 0}
        projectId={data?.projectId ?? null}
        onNotice={setNotice}
      />

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
          正在加载文档…
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
          <ResultPanel
            extractions={data.extractions}
            index={index}
            rerunModes={rerunModes}
            projectId={data.projectId}
            busyExtractionId={busyExtractionId}
            onLocate={handleLocate}
            onReview={handleReview}
            onRerun={handleRerun}
            onBatchConfirm={handleBatchConfirm}
            onRefresh={async () => {
              await refreshWorkbench();
            }}
            onNotice={setNotice}
            onLoadAttempts={loadAttempts}
          />
        </div>
      )}
    </div>
  );
}
