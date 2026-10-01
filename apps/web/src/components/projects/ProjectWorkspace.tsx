"use client";

/**
 * 项目工作台：文件切换 + 左原文右结果（设计文档 06 第 1 节的 /projects/[id]）。
 *
 * 为什么文件切换竖排在左边而不是横排在顶部：一个项目下往往有主文件、补遗、澄清好几份，
 * 核对同一字段时要来回切。竖排后每份文件都能带一条完整的流水线状态和名字（横排只能在
 * 40px 高的条里塞一行小字），而且切文件切的是「翻哪一卷」，跟左边翻卷宗的心智模型一致。
 *
 * 当前文件走 URL 的 ?file=，而不是组件状态：这样从文件管理页点「打开工作台」直接落到
 * 对应文件，刷新也不会跳回第一份（复制链接给同事也是同一份）。
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppRail } from "@/components/AppRail";
import { FilePipeline, SPINE_CLASS } from "@/components/projects/FilePipeline";
import { DocumentWorkbench } from "@/components/workbench/DocumentWorkbench";
import { BUTTON_CLASS, DATA_CLASS, EYEBROW_CLASS, PRIMARY_BUTTON_CLASS } from "@/components/ui";
import { loadProject } from "@/lib/api/client";
import { formatTime } from "@/lib/format";
import { derivePipeline } from "@/lib/projects/pipeline";
import type { WireProjectDetail } from "@/types/projects";

interface Props {
  projectId: number;
}

export function ProjectWorkspace({ projectId }: Props) {
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
    reload().catch((caught: unknown) => {
      if (alive) setError(caught instanceof Error ? caught.message : "加载项目失败");
    });
    return () => {
      alive = false;
    };
  }, [reload]);

  // 有版本的文件才能进工作台：没有版本的还在转换，切过去只会看到加载失败。
  const openable = (project?.files ?? []).filter((file) => file.version_id !== null);
  const active = openable.find((file) => file.project_file_id === requested) ?? openable[0] ?? null;

  const select = (fileId: number) => {
    router.replace("/projects/" + projectId + "?file=" + fileId, { scroll: false });
  };

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <AppRail />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-5 py-2.5">
          <Link
            href="/projects"
            className="text-[13px] text-slate-400 transition-colors hover:text-sky-700"
          >
            项目
          </Link>
          <span aria-hidden className="text-slate-300">
            /
          </span>
          <h1 className="max-w-96 truncate font-serif text-[15px] leading-6 text-slate-900">
            {project?.name ?? "…"}
          </h1>
          <div className="ml-auto flex items-center gap-2">
            <Link href={"/projects/" + projectId + "/files"} className={BUTTON_CLASS}>
              文件管理
            </Link>
            <button
              type="button"
              className={BUTTON_CLASS}
              onClick={() => void reload().catch(() => setError("刷新失败"))}
            >
              刷新
            </button>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <aside className="hidden w-[228px] shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
            <div className="flex items-baseline justify-between px-4 pt-3.5 pb-2">
              <p className={EYEBROW_CLASS}>本项目文件</p>
              <span className={DATA_CLASS + " text-[11px] text-slate-400"}>
                {(project?.files ?? []).length}
              </span>
            </div>
            <ul className="min-h-0 flex-1 overflow-y-auto border-t border-slate-100">
              {(project?.files ?? []).map((file) => {
                const isActive = active !== null && file.project_file_id === active.project_file_id;
                const pipeline = derivePipeline(file);
                const disabled = file.version_id === null;
                return (
                  <li key={file.project_file_id} className="border-b border-slate-100">
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => select(file.project_file_id)}
                      title={disabled ? "还在转换，完成后才能打开" : pipeline.headline}
                      aria-current={isActive ? "true" : undefined}
                      className={
                        "relative flex w-full flex-col gap-1.5 px-4 py-2.5 text-left transition-colors " +
                        (isActive ? "bg-slate-50" : "hover:bg-slate-50/70") +
                        (disabled ? " cursor-not-allowed opacity-45" : "")
                      }
                    >
                      {isActive && (
                        <span
                          aria-hidden
                          className="absolute inset-y-0 left-0 w-[4px] bg-amber-400"
                        />
                      )}
                      <span
                        className={
                          "truncate font-serif text-[14px] leading-5 " +
                          (isActive ? "text-slate-900" : "text-slate-600")
                        }
                      >
                        {file.display_name}
                      </span>
                      <span className="flex items-center gap-2">
                        {file.is_parseable ? (
                          <FilePipeline file={file} compact />
                        ) : (
                          <span
                            aria-hidden
                            className={"h-[7px] w-[14px] " + SPINE_CLASS.idle}
                          />
                        )}
                        <span className="truncate text-[11px] text-slate-400">
                          {file.is_parseable ? pipeline.headline : "仅归档"}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="border-t border-slate-200 p-2">
              <Link
                href={"/projects/" + projectId + "/files"}
                className={BUTTON_CLASS + " w-full"}
              >
                上传 / 管理文件
              </Link>
            </div>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            {error !== null && (
              <div className="border-b border-rose-200 bg-rose-50 px-5 py-2 text-[14px] text-rose-700">
                {error}
              </div>
            )}

            {project === null ? (
              <div className="flex flex-1 items-center justify-center text-[14px] text-slate-500">
                正在加载项目…
              </div>
            ) : active === null ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 bg-white text-center">
                <p className="font-serif text-[19px] text-slate-900">
                  {project.files.length === 0 ? "这个项目还没有文件" : "文件还在转换"}
                </p>
                <p className="max-w-md text-[14px] leading-6 text-slate-500">
                  原文与抽取结果的核对需要先有一份可渲染的 PDF，Office 文件要走一次格式转换。
                  转换完成前，这里没有可以摊开的纸。
                </p>
                <Link
                  href={"/projects/" + projectId + "/files"}
                  className={PRIMARY_BUTTON_CLASS + " mt-1 px-4 py-2"}
                >
                  {project.files.length === 0 ? "去上传文件" : "查看转换进度"}
                </Link>
              </div>
            ) : (
              <>
                {/* 版本行：机读事实（版本号 / 页数 / 哈希）用等宽，人读状态用流水线。 */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-slate-200 bg-white px-5 py-1.5 text-[13px] text-slate-500">
                  <span className={DATA_CLASS}>
                    版本 #{active.version_id}
                  </span>
                  <span className={DATA_CLASS}>{active.page_count ?? 0} 页</span>
                  <span className={DATA_CLASS} title={"SHA-256 " + active.sha256}>
                    {active.sha256.slice(0, 12)}
                  </span>
                  <span className="text-slate-300">·</span>
                  <span>{formatTime(active.created_at)} 入库</span>
                  <span className="ml-auto">
                    <FilePipeline file={active} />
                  </span>
                </div>
                <div className="min-h-0 flex-1">
                  <DocumentWorkbench
                    versionId={active.version_id as number}
                    /* 复核 / 重跑落定后重取项目：左侧文件栏的流水线与待复核数要跟着动 */
                    onSettled={() => void reload().catch(() => undefined)}
                  />
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
