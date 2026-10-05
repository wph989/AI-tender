"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppRail } from "@/components/AppRail";
import { Icon } from "@/components/Icon";
import { ProjectAnalysis } from "@/components/knowledge/ProjectAnalysis";
import { FilePipeline } from "@/components/projects/FilePipeline";
import { DocumentWorkbench } from "@/components/workbench/DocumentWorkbench";
import { BUTTON_CLASS, GHOST_BUTTON_CLASS, PRIMARY_BUTTON_CLASS } from "@/components/ui";
import { loadProject } from "@/lib/api/client";
import { derivePipeline } from "@/lib/projects/pipeline";
import type { WireProjectDetail } from "@/types/projects";

/** 文件以横向标签切换，将横向空间优先留给原文与证据；URL 仍保留当前文件。 */
export function ProjectWorkspace({ projectId }: { projectId: number }) {
  const params = useSearchParams();
  return params.get("view") === "fields" || params.has("file")
    ? <FileWorkspace projectId={projectId} /> : <ProjectAnalysis key={projectId} projectId={projectId} />;
}

function FileWorkspace({ projectId }: { projectId: number }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requested = Number(searchParams.get("file") ?? "");
  const [project, setProject] = useState<WireProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    const detail = await loadProject(projectId);
    setProject(detail);
    setError(null);
    return detail;
  }, [projectId]);
  useEffect(() => {
    let alive = true;
    reload().catch((caught: unknown) => { if (alive) setError(caught instanceof Error ? caught.message : "加载项目失败"); });
    return () => { alive = false; };
  }, [reload]);

  // 等待转换时自动发现可打开的版本，用户无需反复刷新。
  const inFlight = project?.files.some((file) => derivePipeline(file).inFlight) ?? false;
  useEffect(() => {
    if (!inFlight) return;
    const timer = window.setInterval(() => { void reload().catch(() => undefined); }, 5000);
    return () => window.clearInterval(timer);
  }, [inFlight, reload]);
  const openable = (project?.files ?? []).filter((file) => file.version_id !== null);
  const active = openable.find((file) => file.project_file_id === requested) ?? openable[0] ?? null;

  return (
    <div className="workspace">
      <AppRail />
      <header className="workspace-heading">
        <Link href="/projects" className="back-button" aria-label="返回项目空间"><Icon name="back" size={16} /></Link>
        <div className="min-w-0"><p className="mb-0.5 text-[10px] text-slate-400">项目空间 / 核对工作台</p><h1>{project?.name ?? "正在加载项目…"}</h1></div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <Link href={"/projects/" + projectId} className={BUTTON_CLASS}>综合分析</Link>
          <button type="button" className={GHOST_BUTTON_CLASS} aria-label="刷新项目" onClick={() => void reload().catch(() => setError("刷新失败，请重试"))}><Icon name="refresh" size={16} /></button>
          <Link href={"/projects/" + projectId + "/files"} className={BUTTON_CLASS}><Icon name="upload" size={15} /><span>文件管理</span></Link>
        </div>
      </header>
      {project !== null && project.files.length > 0 && <nav aria-label="项目文件" className="workspace-tabs">
        {project.files.map((file) => <button key={file.project_file_id} type="button" className="workspace-file"
          aria-current={active?.project_file_id === file.project_file_id ? "true" : undefined}
          disabled={file.version_id === null} title={file.display_name + " · " + derivePipeline(file).headline}
          onClick={() => router.replace("/projects/" + projectId + "?file=" + file.project_file_id, { scroll: false })}>
          <Icon name="file" size={15} /><span className="truncate">{file.display_name}</span>
          <FilePipeline file={file} compact />
        </button>)}
      </nav>}
      <main id="main-content" tabIndex={-1} className="workspace-body">
        {error && <div role="alert" className="notice mb-3"><Icon name="alert" /><span className="flex-1">{error}</span><button type="button" className={BUTTON_CLASS} onClick={() => void reload().catch(() => setError("重试失败，请稍后重试"))}>重试</button></div>}
        {project === null ? <div role="status" className="empty-state flex-1"><span className="empty-icon"><Icon name="folder" size={28} /></span><p>{error ? "项目暂时无法打开，请重试。" : "正在打开项目文件…"}</p></div>
          : active === null ? <div className="empty-state flex-1">
            <span className="empty-icon"><Icon name="upload" size={28} /></span>
            <h2>{project.files.length === 0 ? "准备好第一份招标文件" : inFlight ? "文件正在准备中" : "暂无可预览的文档"}</h2>
            <p>{project.files.length === 0 ? "上传文件后，关键条款与对应原文会在这里一同呈现。" : inFlight ? "文件转换完成后即可打开原文，处理进度会自动更新。" : "请在文件管理中查看失败原因，或上传可解析的文档；仅归档文件不生成预览。"}</p>
            <Link href={"/projects/" + projectId + "/files"} className={PRIMARY_BUTTON_CLASS}>{project.files.length === 0 ? "上传文件" : "查看处理进度"}<Icon name="arrow" size={16} /></Link>
          </div>
          : <DocumentWorkbench key={active.version_id} versionId={active.version_id as number}
              refreshToken={[active.latest_job?.id, active.latest_job?.status, active.latest_job?.stage, active.latest_run_id, active.extraction_count].join(":")}
              onSettled={() => void reload().catch(() => undefined)} />}
      </main>
    </div>
  );
}
