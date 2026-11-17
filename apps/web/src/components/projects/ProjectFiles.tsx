"use client";
import { App, Button, Modal, Select, Space, Input, Tag } from "antd";
import { useFeedback } from "@/hooks/useFeedback";

/** 文件管理保留上传、重跑与角色变更接口，用统一表格承载处理进度和操作。 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { DataTable } from "@/components/DataTable";
import { FileEditModal } from "./FileEditModal";
import { PageShell } from "@/components/PageShell";
import { FilePipeline } from "@/components/projects/FilePipeline";
import {
  UploadPanel,
  type UploadOptionsState,
} from "@/components/projects/UploadPanel";
import {
  PRIMARY_BUTTON_CLASS,
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
} from "@/lib/projects/pipeline";
import {
  FILE_ROLE_LABELS,
  type FileRole,
  type OcrMode,
  type ParseTier,
  type UploadResult,
  type WireProjectDetail,
  type WireProjectFile,
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
  const [search, setSearch] = useState("");
  const [fileEditor, setFileEditor] = useState<{ file: WireProjectFile; mode: "rename" | "replace" } | null>(null);
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
      setProject((current) => current ? { ...current,
        files: current.files.filter((file) => file.project_file_id !== fileId) } : current);
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
        <section aria-label="文件清单">
          <div className="list-toolbar">
            <h2>
              文件清单 <span className="table-meta">{files.length} 份</span>
            </h2>
            <Input.Search
              aria-label="搜索文件"
              placeholder="搜索文件名称"
              allowClear
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              style={{ width: 300, maxWidth: "100%" }}
            />
          </div>
          <DataTable<WireProjectFile>
            rowKey="project_file_id"
            dataSource={files.filter((file) =>
              file.display_name
                .toLowerCase()
                .includes(search.trim().toLowerCase()),
            )}
            pagination={{ defaultPageSize: 10 }}
            scroll={{ x: 1100 }}
            columns={[
              {
                title: "文件名称",
                key: "name",
                width: 300,
                render: (_, file) => (
                  <div>
                    <strong className="table-title">
                      {file.display_name}
                    </strong>
                    <div className="table-meta">
                      {formatBytes(file.size_bytes)} ·{" "}
                      {file.page_count ?? "—"} 页 ·{" "}
                      {formatTime(file.created_at)}
                    </div>
                    {file.replaced_by_id !== null && <Tag>已换版</Tag>}
                    {!file.is_parseable && <Tag>仅归档</Tag>}
                  </div>
                ),
              },
              {
                title: "文件角色",
                key: "role",
                width: 140,
                render: (_, file) => (
                  <Select
                    value={file.role}
                    aria-label={`「${file.display_name}」的角色`}
                    disabled={
                      busyFileId !== null || busy || fileEditor !== null
                    }
                    options={Object.entries(FILE_ROLE_LABELS).map(
                      ([value, label]) => ({ value, label }),
                    )}
                    onChange={(value) =>
                      void handleRole(
                        file.project_file_id,
                        value as FileRole,
                      )
                    }
                  />
                ),
              },
              {
                title: "处理状态",
                key: "pipeline",
                width: 300,
                render: (_, file) => (
                  <div>
                    {file.is_parseable ? (
                      <FilePipeline file={file} />
                    ) : (
                      <span className="table-meta">不参与文本解析</span>
                    )}
                    {file.latest_job &&
                      ["failed", "canceled"].includes(
                        file.latest_job.status,
                      ) && (
                        <p role="alert" className="mt-2 text-xs text-rose-700">
                          {file.latest_job.error_message ??
                            file.latest_job.error_code ??
                            "任务未完成，请重试"}
                        </p>
                      )}
                  </div>
                ),
              },
              {
                title: "操作",
                key: "actions",
                fixed: "right",
                width: 300,
                render: (_, file) => (
                  <Space size={4} wrap>
                    {file.version_id !== null && (
                      <Button
                        type="link"
                        href={`/projects/${projectId}?file=${file.project_file_id}`}
                      >
                        预览原文
                      </Button>
                    )}
                    <Button
                      type="link"
                      href={`/api/v1/projects/${projectId}/files/${file.project_file_id}/original`}
                      download
                    >
                      下载原件
                    </Button>
                    <Button
                      type="text"
                      disabled={busy || busyFileId !== null}
                      onClick={() => setFileEditor({ file, mode: "rename" })}
                    >
                      重命名
                    </Button>
                    <Button
                      type="text"
                      disabled={
                        busy ||
                        busyFileId !== null ||
                        derivePipeline(file).inFlight ||
                        file.replaced_by_id !== null
                      }
                      onClick={() => setFileEditor({ file, mode: "replace" })}
                    >
                      上传新版本
                    </Button>
                    {file.version_id !== null && file.is_parseable && (
                      <Button
                        disabled={
                          busy ||
                          busyFileId !== null ||
                          derivePipeline(file).inFlight
                        }
                        onClick={() =>
                          setReparseTarget({
                            fileId: file.project_file_id,
                            versionId: file.version_id!,
                            fileName: file.display_name,
                            tier: file.parse_tier ?? "standard",
                            ocrMode: file.parse_ocr_mode ?? "auto",
                          })
                        }
                      >
                        重新解析
                      </Button>
                    )}
                    <Button
                      type="text"
                      danger
                      disabled={busy || busyFileId !== null}
                      onClick={() =>
                        void handleDelete(
                          file.project_file_id,
                          file.display_name,
                        )
                      }
                    >
                      删除
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </section>
      )}
      {fileEditor && (
        <FileEditModal
          projectId={projectId}
          {...fileEditor}
          onClose={() => setFileEditor(null)}
          onSaved={reload}
        />
      )}
    </PageShell>
  );
}
