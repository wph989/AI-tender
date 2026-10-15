"use client";
import { App, Button, Modal, Select } from "antd";
import { useFeedback } from "@/hooks/useFeedback";

/** 文件管理保留上传、重跑与角色变更接口，用文件卡片承载处理进度和操作。 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { PageShell } from "@/components/PageShell";
import { FilePipeline, SPINE_CLASS } from "@/components/projects/FilePipeline";
import {
  UploadPanel,
  type UploadOptionsState,
} from "@/components/projects/UploadPanel";
import {
  DATA_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECTION_TITLE_CLASS,
} from "@/components/ui";
import {
  deleteProjectFile,
  loadProject,
  patchProjectFile,
  reparseVersion,
  uploadProjectFiles,
  waitForJob,
} from "@/lib/api/client";
import { formatBytes, formatTime } from "@/lib/format";
import {
  derivePipeline,
  needsReparse,
} from "@/lib/projects/pipeline";
import {
  FILE_ROLE_LABELS,
  type FileRole,
  type OcrMode,
  type ParseTier,
  type UploadResult,
  type WireProjectDetail,
} from "@/types/projects";

const POLL_MS = 4000;

/** 文档解析可能较慢，超时后由列表轮询继续跟进。 */
const VERSION_JOB_TIMEOUT_MS = 20 * 60 * 1000;

/** 重新解析会生成新的原文定位，提交前展示影响说明。 */
interface ReparseTarget {
  fileId: number;
  versionId: number;
  fileName: string;
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
  const { modal, message: toast } = App.useApp();
  const [project, setProject] = useState<WireProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyFileId, setBusyFileId] = useState<number | null>(null);
  const [reparseTarget, setReparseTarget] = useState<ReparseTarget | null>(
    null,
  );
  useFeedback(error, notice);
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
      if (alive)
        setError(caught instanceof Error ? caught.message : "加载项目失败");
    });
    return () => {
      alive = false;
    };
  }, [reload]);

  // 只有在跑的文件才值得轮询；全部落定后要立刻停表，否则页面永远在悄悄请求。
  const inFlight = (project?.files ?? []).some(
    (file) => derivePipeline(file).inFlight,
  );
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

  /**
   * 上传一批文件。
   *
   * 出错时既挂横幅、也继续往外抛：横幅是页面级的「这次操作失败了」，交件台还要用这份错误
   * 把逐文件原因摊回对应的行（整批都被拒时，后端把原因放在 error.detail.skipped 里）。
   */
  const handleUpload = async (
    files: File[],
    archive: File | null,
    options: UploadOptionsState,
    onProgress: (ratio: number) => void,
  ): Promise<UploadResult> => {
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
        onProgress,
      );
      setNotice(
        result.jobs.length === 0
          ? `已归档 ${result.added.length} 个文件，无需解析`
          : options.autoParse
            ? `已入库 ${result.added.length} 个文件，正在转换与解析…`
            : `已入库 ${result.added.length} 个文件（未自动解析）`,
      );
      // 入库已成功：后续列表刷新失败不能把上传回执变成失败，导致用户重复上传。
      await reload().catch(() =>
        setError("文件已上传，但列表刷新失败，请点击刷新查看。"),
      );
      return result;
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "上传失败");
      throw caught;
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
    const confirmed = await modal.confirm({
      title: `删除「${name}」？`,
      content: "此文件将退出项目资料，依赖它的报告引用会标记为不可用。",
      okText: "删除",
      okButtonProps: { danger: true },
    });
    if (!confirmed) return;
    setBusyFileId(fileId);
    try {
      await deleteProjectFile(projectId, fileId);
      void toast.success("文件已删除");
      await reload().catch(() =>
        setError("文件已删除，刷新列表失败，请点击刷新。"),
      );
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "删除失败");
    } finally {
      setBusyFileId(null);
    }
  };

  /** 沿用档位和 OCR 模式，避免修复解析时意外改变解析策略。 */
  const handleReparse = async () => {
    const target = reparseTarget;
    if (target === null) return;
    setReparseTarget(null);
    setBusyFileId(target.fileId);
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

  const files = project?.files ?? [];
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
      description="集中管理主文件、补遗与澄清材料，跟进每份文件的分析进度。"
      actions={
        <>
          <Button
            htmlType="button"

            onClick={() => void reload().catch(() => setError("刷新失败"))}
          >
            刷新
          </Button>
          {/* 项目默认页展示综合分析，原文预览需要显式指定文档视图。 */}
          <Link
            href={"/projects/" + projectId + "?view=document"}
            className={PRIMARY_BUTTON_CLASS}
          >
            预览原文
          </Link>
        </>
      }
    >
      {error !== null && (
        <div className="flex items-start gap-3 border border-rose-200 bg-rose-50 px-3 py-2 text-[14px] text-rose-700">
          <span className="flex-1">{error}</span>
          <button
            type="button"
            className="text-[13px] text-rose-700"
            onClick={() => setError(null)}
          >
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

      <Modal
        title="确认重新解析"
        open={reparseTarget !== null}
        centered
        mask={{ closable: false }}
        onCancel={() => setReparseTarget(null)}
        okText="确认重新解析"
        okButtonProps={{ danger: true, disabled: busyFileId !== null }}
        onOk={() => void handleReparse()}
      >
        <p>
          「{reparseTarget?.fileName}」将重新生成解析批次和原文位置。
          已有报告保留原批次引用；需要使用新解析内容时，请重新运行项目分析。
        </p>
      </Modal>

      <div className="file-overview" aria-label="文件概览">
        <span>
          <Icon name="file" size={15} />
          文件 <strong>{project === null ? "—" : files.length}</strong>
        </span>
        <span>
          <Icon name="scan" size={15} />
          处理中 <strong>{project === null ? "—" : running}</strong>
        </span>
        <span>
          <Icon name="clock" size={15} />
          已就绪 <strong>{project === null ? "—" : files.filter((file) => ["completed", "partial"].includes(file.parse_status ?? "")).length}</strong>
        </span>
      </div>
      <UploadPanel busy={busy} onUpload={handleUpload} />

      {/* 被拒文件的原因由交件台的逐行结果承接（见 UploadPanel）：同一份信息不写两处，
          否则两边的名单迟早对不上。 */}

      {project === null && !error && (
        <p className="text-[14px] text-slate-500">正在加载文件清单…</p>
      )}

      {project !== null && files.length === 0 && (
        <div className="empty-state">
          <p className="font-display font-semibold text-[19px] text-slate-900">
            这个项目还没有文件
          </p>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate-500">
            在上方选择或拖入招标文件，上传后即可在这里查看进度。
          </p>
        </div>
      )}

      {files.length > 0 && (
        <section className="files-panel">
          <header className="flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-slate-200 px-5 py-3">
            <div>
              <h2 className={SECTION_TITLE_CLASS + " mt-1"}>文件清单</h2>
            </div>
            <span className={DATA_CLASS + " pb-0.5 text-[13px] text-slate-400"}>
              {files.length} 个
            </span>
            {/* 图例放在流水线旁边，而不是页脚：读者看到色块的那一刻就能查到它什么意思 */}
            <ul className="ml-auto flex items-center gap-3 pb-0.5 text-[13px] text-slate-400">
              {(
                [
                  ["idle", "未开始"],
                  ["active", "进行中"],
                  ["done", "已完成"],
                  ["failed", "失败"],
                ] as const
              ).map(([state, label]) => (
                <li key={state} className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className={"h-[7px] w-[7px] " + SPINE_CLASS[state]}
                  />
                  {label}
                </li>
              ))}
            </ul>
          </header>

          <ul>
            {files.map((file) => {
              const fileBusy = busyFileId !== null;
              return (
                <li
                  key={file.project_file_id}
                  className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/70"
                >
                  <div className="file-entry">
                    <div className="file-entry-name">
                      <span className="file-type-icon">
                        <Icon name="file" size={22} />
                      </span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className="min-w-0 break-all font-display font-semibold text-[14px] leading-6 text-slate-900"
                            title={file.display_name}
                          >
                            {file.display_name}
                          </span>
                          {/* 文档种类：扫清单时先看它是主文件还是补遗/澄清，比读下拉框快 */}
                          <span className="shrink-0 border border-slate-300 px-1 py-px text-[11px] text-slate-600">
                            {FILE_ROLE_LABELS[file.role as FileRole] ??
                              file.role}
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

                          <span>{formatTime(file.created_at)}</span>
                          <label className="flex items-center gap-1.5 text-slate-400">
                            <span className="font-sans">角色</span>
                            <Select<string>
                              value={String(file.role)}
                              disabled={fileBusy}
                              aria-label={"「" + file.display_name + "」的角色"}
                              onChange={(selectedValue) =>
                                void handleRole(
                                  file.project_file_id,
                                  selectedValue as FileRole,
                                )
                              }
                              className={
                                "" +
                                " py-0.5 pl-1.5 text-[13px] font-sans text-slate-600"
                              }
                            >
                              {(
                                Object.keys(FILE_ROLE_LABELS) as FileRole[]
                              ).map((role) => (
                                <Select.Option key={role} value={String(role)}>
                                  {FILE_ROLE_LABELS[role]}
                                </Select.Option>
                              ))}
                            </Select>
                          </label>
                        </div>
                      </div>
                    </div>
                    <div>
                      {file.is_parseable ? (
                        <FilePipeline file={file} />
                      ) : (
                        <span className="text-[13px] text-slate-400">
                          不参与文本解析
                        </span>
                      )}
                      {file.latest_job &&
                        ["failed", "canceled"].includes(
                          file.latest_job.status,
                        ) && (
                          <p
                            className="mt-2 max-w-sm break-words text-[12px] text-rose-700"
                            role="alert"
                          >
                            {file.latest_job.error_message ??
                              file.latest_job.error_code ??
                              "任务未完成，请检查服务后重试。"}
                          </p>
                        )}
                    </div>

                    <div className="file-entry-actions">
                      {file.version_id === null ? (
                        <span className="text-[13px] text-slate-400">
                          {file.is_parseable ? "暂无预览" : "仅归档"}
                        </span>
                      ) : (
                        <Link
                          href={
                            "/projects/" +
                            projectId +
                            "?file=" +
                            file.project_file_id
                          }
                          className="whitespace-nowrap rounded-lg px-1.5 py-0.5 text-[13px] text-sky-700 hover:bg-sky-50 hover:underline"
                        >
                          预览原文
                        </Link>
                      )}
                      {file.version_id !== null && file.is_parseable && (
                        <>
                          <Button
                            type="primary"
                            htmlType="button"
                            className={needsReparse(file) ? "" : ""}
                            disabled={fileBusy || derivePipeline(file).inFlight}
                            onClick={() =>
                              setReparseTarget({
                                fileId: file.project_file_id,
                                versionId: file.version_id as number,
                                fileName: file.display_name,
                                tier: file.parse_tier ?? "standard",
                                ocrMode: file.parse_ocr_mode ?? "auto",
                              })
                            }
                          >
                            重新解析
                          </Button>
                        </>
                      )}
                      <Button
                        danger
                        type="text"
                        htmlType="button"

                        disabled={fileBusy}
                        onClick={() =>
                          void handleDelete(
                            file.project_file_id,
                            file.display_name,
                          )
                        }
                      >
                        删除
                      </Button>
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
