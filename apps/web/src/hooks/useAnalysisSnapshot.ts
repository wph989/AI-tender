"use client";

import { useCallback, useEffect, useState } from "react";
import { knowledgeRequest } from "@/lib/api/knowledge";
import type { AnalysisDataSnapshot, AnalysisReport } from "@/types/knowledge";

/** 汇总接口只在终态读取；报告切换时隔离旧快照，失败不阻断专题正文。 */
export function useAnalysisSnapshot(report: AnalysisReport) {
  const [snapshot, setSnapshot] = useState<AnalysisDataSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const terminal = !["waiting", "pending", "running"].includes(report.status);
  useEffect(() => {
    setSnapshot(null); setError(null);
    if (!terminal || !report.data_schema_version) {
      setLoading(false); return;
    }
    const abort = new AbortController();
    setLoading(true);
    void knowledgeRequest<AnalysisDataSnapshot>(`/analysis/reports/${report.id}/data`,
      "GET", undefined, abort.signal).then((data) => {
      if (!abort.signal.aborted) setSnapshot(data);
    }).catch((reason) => {
      if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : "汇总核对暂不可用");
    }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [report.id, report.finished_at, report.stale, report.data_schema_version, terminal, revision]);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  return { snapshot: terminal && snapshot?.report_id === report.id ? snapshot : null, error, loading, reload, terminal };
}
