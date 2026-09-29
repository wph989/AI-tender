"use client";

/**
 * 项目导出入口：小项目直接下文件，大项目先排队再下载。
 *
 * 后端超过 2000 行会把导出转成异步任务（见 api/exports.py），返回的是 job 而不是文件；
 * 前端一律当成文件处理的话，用户会下载到一个 JSON。这里按 Content-Type 分流。
 */

import { useState } from "react";

import { downloadExportJob, exportProject, saveBlob, waitForJob } from "@/lib/api/client";

interface Props {
  projectId: number | null;
  onNotice: (message: string | null) => void;
}

export function ExportButton({ projectId, onNotice }: Props) {
  const [busy, setBusy] = useState(false);

  const handleClick = async () => {
    if (projectId === null || busy) return;
    setBusy(true);
    onNotice("正在导出…");
    try {
      const outcome = await exportProject(projectId);
      if (outcome.kind === "file") {
        saveBlob(outcome.blob, outcome.filename);
        onNotice(null);
        return;
      }
      const job = await waitForJob(outcome.jobId, 300_000);
      if (job.status !== "completed") {
        throw new Error(job.error_message ?? "导出任务未完成");
      }
      const file = await downloadExportJob(outcome.jobId);
      saveBlob(file.blob, file.filename);
      onNotice(null);
    } catch (error: unknown) {
      onNotice(error instanceof Error ? error.message : "导出失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={projectId === null || busy}
      title={projectId === null ? "静态样本没有项目，导出不可用" : "导出当前项目的抽取结果"}
      className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40"
    >
      {busy ? "导出中…" : "导出 Excel"}
    </button>
  );
}