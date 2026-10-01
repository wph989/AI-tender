"use client";

/**
 * 文件管理页：交件台 + 文件清单（设计文档 06 第 1 节的 /projects/[id]/files）。
 *
 * 为什么这一页必须存在：工作台是按版本取数的，用户拿到一份标书时还没有版本，
 * 「先转换再解析」这段时间里没有任何界面能承接他——这一页就是那段等待期的落点。
 *
 * 为什么清单不做成表格：一行的信息里有两类东西——「这个文件是什么」（名称、大小、页数、
 * 哈希）和「它跑到哪一步了」（转换/解析/抽取）。表格把后者压成一列窄格子，流水线只能
 * 缩成三个匿名小方块。这里改成一行里分列的块：左边读文件，右边读进度，扫视顺序和
 * 实际工作顺序一致。
 *
 * 轮询只在有文件还在跑的时候开：常驻轮询会让一个没有任务的项目每几秒打一次接口，
 * 而列表页真正的成本不在请求本身，在于用户看到「12 项待复核」这种数字自己在跳。
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { PageShell } from "@/components/PageShell";
import { FilePipeline, SPINE_CLASS } from "@/components/projects/FilePipeline";
import { UploadPanel, type UploadOptionsState } from "@/components/projects/UploadPanel";
import {
  BUTTON_CLASS,
  DATA_CLASS,
  DANGER_GHOST_BUTTON_CLASS,
  GHOST_BUTTON_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECTION_TITLE_CLASS,
  SELECT_CLASS,
} from "@/components/ui";
import {
  deleteProjectFile,
  loadProject,
  patchProjectFile,
  reparseVersion,
  rerunExtractionForVersion,
  uploadProjectFiles,
  waitForJob,
} from "@/lib/api/client";
import { formatBytes, formatTime } from "@/lib/format";
import { derivePipeline, needsExtractRerun, needsReparse } from "@/lib/projects/pipeline";
import {
  FILE_ROLE_LABELS,
  type FileRole,
  type OcrMode,
  type ParseTier,
  type UploadResult,
  type WireProjectDetail,
} from "@/types/projects";

const POLL_MS = 4000;

/**
 * 整份重跑的等待上限：抽取要逐字段过一遍模型（实测 14 个字段约 9 分钟），
 * 默认的 120 秒远远不够。
 */
const VERSION_JOB_TIMEOUT_MS = 20 * 60 * 1000;

/**
 * 待确认的「重新解析」。列表页每一行都可能触发它，而它的代价是重建全部锚点、
 * 把已确认结果打回复核——不能一个点击就落库，所以先挂在状态里出后果横幅。
 */
interface ReparseTarget {
  versionId: number;
  fileName: string;
  /** 该版本上已确认的结果条数：横幅里那个 N。 */
  confirmed: number;
  /**
   * 上一次解析用的档位与 OCR 模式：重新解析是「把这一次修好」，不是顺手换档。
   * 不带上这两个值就会把 advanced / ocr 的文件静默降回默认档（档位变了，用户
   * 比较的前后两次解析结果也就不可比了）。
   */
  tier: ParseTier;
  ocrMode: OcrMode;
}

interface Props {
  projectId: number;
}

export function ProjectFiles({ projectId }: Props) {
  const [project, setProject] = useState<WireProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState<UploadResult | null>(null);
  const [busyFileId, setBusyFileId] = useState<number | null>(null);
  const [reparseTarget, setReparseTarget] = useState<ReparseTarget | null>(null);
  const timer = useRef<number | null>(null);

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

  // 只有在跑的文件才值得轮询；全部落定后要立刻停表，否则页面永远在悄悄请求。
  const inFlight = (project?.files ?? []).some((file) => derivePipeline(file).inFlight);
  useEffect(() => {
    if (!inFlight) return;
    timer.current = window.setInterval(() => {
      void reload().catch(() => undefined);
    }, POLL_MS);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [inFlight, reload]);

  const handleUpload = async (
    files: File[],
    archive: File | null,
    options: UploadOptionsState,
  ) => {
    setBusy(true);
    setNotice(null);
    try {
      const result = await uploadProjectFiles(
        projectId,
        files,
        {
          tier: options.tier,
          ocrMode: options.ocrMode,
          autoParse: options.autoParse,
          role: options.role === "" ? null : options.role,
        },
        archive,
      );
      setLastResult(result);
      setNotice(
        options.autoParse
          ? `已入库 ${result.added.length} 个文件，正在转换与解析…`
          : `已入库 ${result.added.length} 个文件（未自动解析）`,
      );
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "上传失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRole = async (fileId: number, role: FileRole) => {
    setBusyFileId(fileId);
    try {
      await patchProjectFile(projectId, fileId, { role });
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "修改角色失败");
    } finally {
      setBusyFileId(null);
    }
  };

  const handleDelete = async (fileId: number, name: string) => {
    if (!window.confirm(`删除「${name}」？已抽取的结果会一并从清单中移除。`)) return;
    setBusyFileId(fileId);
    try {
      await deleteProjectFile(projectId, fileId);
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "删除失败");
    } finally {
      setBusyFileId(null);
    }
  };

  /**
   * 重新解析：锚点全部重建、已确认结果全部打回复核。
   *
   * 弹横幅而不是直接提交：这是付费最高的一条路（见 docs/设计/05 第 3.11 节），
   * 用户点它之前必须看见「有多少已确认结果会被打回」。
   */
  const handleReparse = async () => {
    const target = reparseTarget;
    if (target === null) return;
    setReparseTarget(null);
    setBusyFileId(target.versionId);
    setNotice("已提交重新解析，锚点将全部重建…");
    try {
      const queued = await reparseVersion(target.versionId, {
        tier: target.tier,
        ocrMode: target.ocrMode,
        reason: "用户在文件清单发起重新解析",
      });
      // 提交后立刻重取一次清单：这一行转为「进行中」后轮询才会接管，
      // 否则整段等待里它还停在提交前的状态，看起来像没提交成功。
      // 刷新失败不该判定为提交失败——任务已经落库了，下一轮轮询会自愈。
      void reload().catch(() => undefined);
      const job = await waitForJob(queued.job_id, VERSION_JOB_TIMEOUT_MS);
      if (job.status === "failed" || job.status === "canceled") {
        throw new Error(job.error_message ?? "重新解析失败");
      }
      await reload();
      setNotice(null);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "重新解析失败");
    } finally {
      setBusyFileId(null);
    }
  };

  /**
   * 重跑抽取：复用最近一次解析产物，不重建锚点、不作废已确认的结果。
   *
   * 这是「解析成功、抽取失败（0 条结果）」的第一出口。不能拿
   * POST /projects/{id}/rerun 代替：那是从已有结果行里筛候选的，一条都没有时返回 queued = 0。
   */
  const handleExtractRerun = async (versionId: number) => {
    setBusyFileId(versionId);
    setNotice("已提交重跑抽取，正在等待结果…");
    try {
      const queued = await rerunExtractionForVersion(versionId);
      // 同上：先把行切到「进行中」，列表页的 4 秒轮询才会开始跑。
      void reload().catch(() => undefined);
      const job = await waitForJob(queued.job_id, VERSION_JOB_TIMEOUT_MS);
      if (job.status === "failed" || job.status === "canceled") {
        throw new Error(job.error_message ?? "重跑抽取失败");
      }
      await reload();
      setNotice(null);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "重跑抽取失败");
    } finally {
      setBusyFileId(null);
    }
  };

  const files = project?.files ?? [];
  const reviewers = files.reduce((sum, file) => sum + file.review_count, 0);
  const running = files.filter((file) => derivePipeline(file).inFlight).length;

  return (
    <PageShell
      breadcrumb={[
        <Link href="/projects" className="hover:text-sky-700">
          项目
        </Link>,
        <span className="text-slate-600">{project?.name ?? "…"}</span>,
        <span>文件</span>,
      ]}
      eyebrow="文件"
      title={project?.name ?? "文件清单"}
      description={
        project === null
          ? "上传招标文件，转换与解析会自动排进队列。"
          : `共 ${files.length} 个文件 · ${reviewers} 项待复核` +
            (running > 0 ? ` · ${running} 个正在跑` : "") +
            "。转换 → 解析 → 抽取 三步跑完，就能打开工作台逐条核对。"
      }
      actions={
        <>
          <button
            type="button"
            className={BUTTON_CLASS}
            onClick={() => void reload().catch(() => setError("刷新失败"))}
          >
            刷新
          </button>
          <Link href={"/projects/" + projectId} className={PRIMARY_BUTTON_CLASS}>
            打开工作台
          </Link>
        </>
      }
    >
      {error !== null && (
        <div className="flex items-start gap-3 border border-rose-200 bg-rose-50 px-3 py-2 text-[14px] text-rose-700">
          <span className="flex-1">{error}</span>
          <button type="button" className="text-[13px] text-rose-700" onClick={() => setError(null)}>
            关闭
          </button>
        </div>
      )}

      {notice !== null && (
        <div className="flex items-start gap-3 border border-amber-200 bg-amber-50 px-3 py-2 text-[14px] text-amber-900">
          <span className="flex-1">{notice}</span>
          <button
            type="button"
            className="text-[13px] text-amber-700"
            onClick={() => setNotice(null)}
          >
            关闭
          </button>
        </div>
      )}

      {/* 后果横幅：重新解析的代价必须先说清楚，再让用户按下去（见 docs/质量/09 第 5.2 节） */}
      {reparseTarget !== null && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border border-rose-200 bg-rose-50 py-2 pr-3 pl-4">
          <span aria-hidden className="h-4 w-[4px] shrink-0 bg-rose-500" />
          <p className="text-[13px] text-rose-800">
            「{reparseTarget.fileName}」将重建全部锚点（页码与 block 编号都可能变），此前{" "}
            <span className={DATA_CLASS + " font-medium"}>{reparseTarget.confirmed}</span>{" "}
            条已确认结果需要重新复核。
          </p>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              className={PRIMARY_BUTTON_CLASS}
              disabled={busyFileId !== null}
              onClick={() => void handleReparse()}
            >
              确认重新解析
            </button>
            <button
              type="button"
              className={BUTTON_CLASS}
              disabled={busyFileId !== null}
              onClick={() => setReparseTarget(null)}
            >
              取消
            </button>
          </div>
        </div>
      )}

      <UploadPanel busy={busy} onUpload={handleUpload} />

      {lastResult !== null && lastResult.skipped.length > 0 && (
        <section className="border border-rose-200 bg-white">
          <div aria-hidden className="h-[3px] bg-rose-500" />
          <div className="px-5 py-4">
            <h2 className={SECTION_TITLE_CLASS}>没有入库的文件</h2>
            <p className="mt-1 text-[13px] text-slate-500">
              这些文件被服务端拒收，需要换格式或改内容后重新上传。
            </p>
            <ul className="mt-3 flex flex-col gap-1">
              {lastResult.skipped.map((item) => (
                <li key={item.name} className="text-[13px] text-slate-600">
                  <span className="text-slate-900">{item.name}</span>
                  <span className="ml-2 text-rose-700">{item.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {project === null && <p className="text-[14px] text-slate-500">正在加载文件清单…</p>}

      {project !== null && files.length === 0 && (
        <div className="border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <p className="font-serif text-[19px] text-slate-900">这个项目还没有文件</p>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate-500">
            把招标文件拖到上面的交件台，转换与解析会自动排进队列；跑完就能打开工作台核对。
          </p>
        </div>
      )}

      {files.length > 0 && (
        <section className="border border-slate-200 bg-white">
          <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-200 px-4 py-2.5">
            <h2 className="text-[14px] font-medium text-slate-700">文件清单</h2>
            <span className={DATA_CLASS + " text-[13px] text-slate-400"}>{files.length} 个</span>
            {/* 图例放在流水线旁边，而不是页脚：读者看到色块的那一刻就能查到它什么意思 */}
            <ul className="ml-auto flex items-center gap-3 text-[13px] text-slate-400">
              {(
                [
                  ["idle", "未开始"],
                  ["active", "进行中"],
                  ["done", "已完成"],
                  ["failed", "失败"],
                ] as const
              ).map(([state, label]) => (
                <li key={state} className="flex items-center gap-1.5">
                  <span aria-hidden className={"h-[7px] w-[7px] " + SPINE_CLASS[state]} />
                  {label}
                </li>
              ))}
            </ul>
          </header>

          <div className="hidden grid-cols-[minmax(0,1fr)_15rem_5.5rem_21rem] items-center gap-x-5 border-b border-slate-100 px-4 py-1.5 text-[13px] text-slate-400 lg:grid">
            <span>文件</span>
            <span>流水线</span>
            <span className="text-right">待复核</span>
            <span className="text-right">操作</span>
          </div>

          <ul>
            {files.map((file) => {
              const pipeline = derivePipeline(file);
              const fileBusy =
                busyFileId === file.project_file_id || busyFileId === file.version_id;
              return (
                <li
                  key={file.project_file_id}
                  className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/70"
                >
                  <div className="relative flex flex-col gap-y-3 px-4 py-3.5 lg:grid lg:grid-cols-[minmax(0,1fr)_15rem_5.5rem_21rem] lg:items-center lg:gap-x-5">
                    <span
                      aria-hidden
                      className={
                        "absolute inset-y-0 left-0 w-[4px] " +
                        (file.is_parseable ? SPINE_CLASS[pipeline.tone] : "bg-slate-300")
                      }
                    />

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className="min-w-0 truncate font-serif text-[15px] leading-6 text-slate-900"
                          title={file.display_name}
                        >
                          {file.display_name}
                        </span>
                        {/* 文档种类：扫清单时先看它是主文件还是补遗/澄清，比读下拉框快 */}
                        <span className="shrink-0 border border-slate-300 px-1 py-px text-[11px] text-slate-600">
                          {FILE_ROLE_LABELS[file.role as FileRole] ?? file.role}
                        </span>
                        {file.replaced_by_id !== null && (
                          <span className="shrink-0 border border-slate-200 px-1 py-px text-[11px] text-slate-500">
                            已换版
                          </span>
                        )}
                        {!file.is_parseable && (
                          <span className="shrink-0 border border-slate-200 px-1 py-px text-[11px] text-slate-500">
                            仅归档
                          </span>
                        )}
                      </div>
                      <div
                        className={
                          DATA_CLASS +
                          " mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-slate-400"
                        }
                        title={"SHA-256 " + file.sha256}
                      >
                        <span>{formatBytes(file.size_bytes)}</span>
                        <span>{file.page_count ?? "—"} 页</span>
                        <span>{file.sha256.slice(0, 10)}</span>
                        <span>{formatTime(file.created_at)}</span>
                        <label className="flex items-center gap-1.5 text-slate-400">
                          <span className="font-sans">角色</span>
                          <select
                            value={file.role}
                            disabled={fileBusy}
                            aria-label={"「" + file.display_name + "」的角色"}
                            onChange={(event) =>
                              void handleRole(file.project_file_id, event.target.value as FileRole)
                            }
                            className={
                              SELECT_CLASS + " py-0.5 pl-1.5 text-[13px] font-sans text-slate-600"
                            }
                          >
                            {(Object.keys(FILE_ROLE_LABELS) as FileRole[]).map((role) => (
                              <option key={role} value={role}>
                                {FILE_ROLE_LABELS[role]}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    </div>

                    <div>
                      {file.is_parseable ? (
                        <FilePipeline file={file} />
                      ) : (
                        <span className="text-[13px] text-slate-400">不参与文本解析</span>
                      )}
                    </div>

                    <div className="text-right">
                      {file.review_count > 0 ? (
                        <span className={DATA_CLASS + " mark-ink px-1 text-[14px] text-slate-900"}>
                          {file.review_count}
                        </span>
                      ) : (
                        <span className={DATA_CLASS + " text-[14px] text-slate-300"}>—</span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-1 lg:flex-nowrap lg:justify-end">
                      {file.version_id === null ? (
                        <span className="text-[13px] text-slate-400">待转换</span>
                      ) : (
                        <Link
                          href={"/projects/" + projectId + "?file=" + file.project_file_id}
                          className="whitespace-nowrap rounded-[2px] px-1.5 py-0.5 text-[13px] text-sky-700 hover:bg-sky-50 hover:underline"
                        >
                          打开工作台
                        </Link>
                      )}
                      {file.version_id !== null && file.is_parseable && (
                        <>
                          {/*
                           * 两种重跑的代价差一个量级（见 docs/设计/05 第 3.11 节），所以是两个按钮：
                           * 抽取没产出时把「重跑抽取」升为主操作——重新解析会白付一次重建锚点的代价。
                           */}
                          <button
                            type="button"
                            className={
                              needsExtractRerun(file) ? PRIMARY_BUTTON_CLASS : GHOST_BUTTON_CLASS
                            }
                            disabled={fileBusy}
                            onClick={() => void handleExtractRerun(file.version_id as number)}
                          >
                            重跑抽取
                          </button>
                          <button
                            type="button"
                            className={needsReparse(file) ? PRIMARY_BUTTON_CLASS : GHOST_BUTTON_CLASS}
                            disabled={fileBusy}
                            onClick={() =>
                              setReparseTarget({
                                versionId: file.version_id as number,
                                fileName: file.display_name,
                                confirmed: file.confirmed_count,
                                tier: file.parse_tier ?? "standard",
                                ocrMode: file.parse_ocr_mode ?? "auto",
                              })
                            }
                          >
                            重新解析
                          </button>
                        </>
                      )}
                      <button
                        type="button"
                        className={DANGER_GHOST_BUTTON_CLASS}
                        disabled={fileBusy}
                        onClick={() => void handleDelete(file.project_file_id, file.display_name)}
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </PageShell>
  );
}
