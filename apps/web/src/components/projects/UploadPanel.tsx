"use client";
import { Alert, App, Button, Checkbox, Progress, Select, Upload } from "antd";

/** 先选择文件再确认上传，让批量回执与解析选项都能在提交前检查。 */

import { useState } from "react";

import { DATA_CLASS } from "@/components/ui";
import { Icon } from "@/components/Icon";
import { UploadRejectedError } from "@/lib/api/client";
import { formatBytes } from "@/lib/format";
import { outcomeOf, type UploadOutcome } from "@/lib/projects/upload";
import {
  FILE_ROLE_LABELS,
  type FileRole,
  type ParseTier,
  type UploadResult,
} from "@/types/projects";

/** accept 只影响文件选择框的默认过滤，真正的准入判断在服务端（后端会逐个校验）。 */
const ACCEPT =
  ".pdf,.doc,.docx,.odt,.rtf,.ppt,.pptx,.odp,.xls,.xlsx,.xlsm,.ods,.dwg,.dxf,.vsd,.vsdx,.zip";

/**
 * 上限口径与后端 project_files.py 的常量一一对应（_MAX_UPLOAD_BYTES 等）。
 * 两处不一致的后果是用户先撞墙、再被告知限制，所以这里写的是服务端的真实数字。
 */
const LIMITS = [
  "单个文件 ≤ 512 MiB",
  "单次合计 ≤ 1 GiB，最多 100 个文件",
  "ZIP ≤ 128 MiB，成员 ≤ 500 个、解压后 ≤ 512 MiB",
];

const ROLE_RULE = "电子表格自动归类为清单，CAD 与 Visio 文件归类为图纸，";

const TIER_OPTIONS: { value: ParseTier; label: string }[] = [
  { value: "flash", label: "flash · 最快" },
  { value: "basic", label: "basic" },
  { value: "standard", label: "standard · 默认" },
  { value: "advanced", label: "advanced · 最准" },
];

export interface UploadOptionsState {
  tier: ParseTier;
  ocrMode: "auto" | "txt" | "ocr";
  autoParse: boolean;
  role: FileRole | "";
}

/** 一批已提交的文件和它最后的下场；提交后保留在这里给用户逐个确认。 */
interface BatchRow {
  file: File;
  outcome: UploadOutcome;
}

const OUTCOME_LABEL: Record<UploadOutcome["state"], string> = {
  added: "已入库",
  skipped: "被拒",
  unknown: "未入库",
};

const OUTCOME_CLASS: Record<UploadOutcome["state"], string> = {
  added: "text-emerald-700",
  skipped: "text-rose-700",
  unknown: "text-slate-500",
};

interface Props {
  busy: boolean;
  /** 返回服务端的汇总结果：交件台要拿它把结论摊回每一行。 */
  onUpload: (
    files: File[],
    archive: File | null,
    options: UploadOptionsState,
    onProgress: (ratio: number) => void,
  ) => Promise<UploadResult>;
}

export function UploadPanel({ busy, onUpload }: Props) {
  const { message } = App.useApp();
  const [error, setError] = useState<string | null>(null);
  const [staged, setStaged] = useState<File[]>([]);
  const [batch, setBatch] = useState<BatchRow[] | null>(null);
  const [ratio, setRatio] = useState<number | null>(null);
  const [options, setOptions] = useState<UploadOptionsState>({
    tier: "standard",
    ocrMode: "auto",
    autoParse: true,
    role: "",
  });

  const stage = (incoming: File[]) => {
    if (busy) return;
    const next = [...staged];
    for (const file of incoming) {
      if (
        !next.some(
          (item) =>
            item.name === file.name &&
            item.size === file.size &&
            item.lastModified === file.lastModified,
        )
      )
        next.push(file);
    }
    const archives = next.filter((file) =>
      file.name.toLowerCase().endsWith(".zip"),
    );
    const problem =
      archives.length > 1
        ? "一次只能上传一个 ZIP，请分批上传。"
        : next.length > 100
          ? "单次最多上传 100 个文件，请分批上传。"
          : next.some(
                (file) =>
                  file.size >
                  (file.name.toLowerCase().endsWith(".zip") ? 128 : 512) *
                    1024 *
                    1024,
              )
            ? "文件超出大小限制：普通文件 512 MiB，ZIP 128 MiB。"
            : next.reduce((sum, file) => sum + file.size, 0) >
                1024 * 1024 * 1024
              ? "单次总大小不能超过 1 GiB。"
              : null;
    if (problem) {
      setError(problem);
      void message.error(problem);
      return;
    }
    setError(null);
    setStaged(next);
    setBatch(null);
  };

  const reset = () => {
    setBatch(null);
    setStaged([]);
    setRatio(null);
  };

  const submit = async () => {
    if (staged.length === 0 || busy) return;
    const pending = staged;
    const archive =
      pending.find((file) => file.name.toLowerCase().endsWith(".zip")) ?? null;
    const files = pending.filter((file) => file !== archive);
    setRatio(0);
    setError(null);
    try {
      const result = await onUpload(files, archive, options, setRatio);
      setBatch(
        pending.map((file) => ({
          file,
          outcome: outcomeOf(file.name, result),
        })),
      );
      setStaged([]);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "上传失败，请重试。");
      // 整批都没入库时后端仍会回逐文件原因，摊回每一行；其余错误由页面顶部的横幅承接。
      if (caught instanceof UploadRejectedError) {
        const rejected: UploadResult = {
          added: [],
          jobs: [],
          skipped: caught.skipped,
        };
        setBatch(
          pending.map((file) => ({
            file,
            outcome: outcomeOf(file.name, rejected),
          })),
        );
        setStaged([]);
      }
    } finally {
      setRatio(null);
    }
  };

  return (
    <section className="upload-panel" aria-label="上传文件">
      <Upload.Dragger
        accept={ACCEPT}
        multiple
        disabled={busy}
        fileList={[]}
        showUploadList={false}
        beforeUpload={(file, files) => {
          if (file === files[0]) stage(files);
          return false;
        }}
      >
        <span className="upload-icon">
          <Icon name="upload" size={25} />
        </span>
        <p className="ant-upload-text">点击或拖入文件，添加到待上传列表</p>
        <p className="ant-upload-hint">
          支持 PDF、Word、PPT 或 ZIP 招标包；清单与图纸可一同归档。
        </p>
      </Upload.Dragger>
      {error && <Alert className="my-3" type="error" showIcon title={error} />}
      {staged.length > 0 && (
        <div className="my-4 flex justify-end">
          <Button type="primary" loading={busy} onClick={() => void submit()}>
            上传 {staged.length} 个文件
          </Button>
        </div>
      )}
      <details className="upload-settings">
        <summary>
          解析选项与上传限制{" "}
          <span className="ml-2 text-slate-400">
            默认自动识别，上传后开始解析
          </span>
        </summary>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-2 text-[12px] text-slate-500">
            解析档位
            <Select<string>
              aria-label="解析档位"
              disabled={busy}
              value={String(options.tier)}
              onChange={(selectedValue) =>
                setOptions({ ...options, tier: selectedValue as ParseTier })
              }
            >
              {TIER_OPTIONS.map((item) => (
                <Select.Option key={item.value} value={String(item.value)}>
                  {item.label}
                </Select.Option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-2 text-[12px] text-slate-500">
            文字识别
            <Select<string>
              aria-label="文字识别"
              disabled={busy}
              value={String(options.ocrMode)}
              onChange={(selectedValue) =>
                setOptions({
                  ...options,
                  ocrMode: selectedValue as "auto" | "txt" | "ocr",
                })
              }
            >
              <Select.Option value="auto">自动判断</Select.Option>
              <Select.Option value="txt">使用文本层</Select.Option>
              <Select.Option value="ocr">强制 OCR 识别</Select.Option>
            </Select>
          </label>
          <label className="flex flex-col gap-2 text-[12px] text-slate-500">
            文件角色
            <Select<string>
              aria-label="文件角色"
              disabled={busy}
              value={String(options.role)}
              onChange={(selectedValue) =>
                setOptions({ ...options, role: selectedValue as FileRole | "" })
              }
            >
              <Select.Option value="">自动判断</Select.Option>
              {(Object.keys(FILE_ROLE_LABELS) as FileRole[]).map((role) => (
                <Select.Option key={role} value={String(role)}>
                  {FILE_ROLE_LABELS[role]}
                </Select.Option>
              ))}
            </Select>
          </label>
          <Checkbox
            disabled={busy}
            checked={options.autoParse}
            onChange={(event) =>
              setOptions({ ...options, autoParse: event.target.checked })
            }
          >
            上传后自动解析
          </Checkbox>
        </div>
        <ul className="mt-4 flex flex-col gap-1 text-[11px] text-slate-400">
          {LIMITS.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-slate-400">
          {ROLE_RULE}其他文件归为主文件。上传后可调整。
        </p>
      </details>

      {staged.length > 0 && (
        <div className="border-t border-slate-200">
          {ratio !== null && (
            <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 bg-slate-50 px-5 py-2 text-[13px] text-slate-600">
              <span>正在上传</span>
              <Progress
                style={{ width: 220, maxWidth: "100%" }}
                percent={Math.round(ratio * 100)}
                aria-label="上传进度"
              />
              {/* 进度条只走到「字节发完」为止；入库、建版本、派任务都在服务端，还要等一会儿 */}
              <span className="text-slate-400">
                传完还要在服务端逐个入库，请稍等
              </span>
            </div>
          )}
          <ul>
            {staged.map((file) => (
              <li
                key={file.name + "|" + file.size}
                className="flex items-center gap-3 border-b border-slate-100 px-5 py-1.5 text-[13px] last:border-b-0"
              >
                <span className="min-w-0 flex-1 truncate text-slate-700">
                  {file.name}
                </span>
                <span className={DATA_CLASS + " text-slate-500"}>
                  {formatBytes(file.size)}
                </span>
                <span className="w-16 text-right text-slate-400">
                  {ratio === null ? "待上传" : "上传中"}
                </span>
                <button
                  type="button"
                  className="text-slate-400 hover:text-rose-600"
                  disabled={busy}
                  aria-label={"移除 " + file.name}
                  onClick={() =>
                    setStaged(staged.filter((item) => item !== file))
                  }
                >
                  移除
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {batch !== null && (
        <div className="border-t border-slate-200">
          <div className="flex items-center gap-3 border-b border-slate-100 bg-slate-50 px-5 py-2 text-[13px]">
            <span className="text-slate-600">上次提交</span>
            <span className="text-slate-400">
              入库 {batch.filter((row) => row.outcome.state === "added").length}{" "}
              个， 未入库{" "}
              {batch.filter((row) => row.outcome.state !== "added").length} 个
            </span>
            <button
              type="button"
              className="ml-auto text-slate-500 hover:text-slate-900"
              onClick={reset}
            >
              清空
            </button>
          </div>
          <ul>
            {batch.map(({ file, outcome }) => (
              <li
                key={file.name + "|" + file.size}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-100 px-5 py-2 text-[13px] last:border-b-0"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-slate-700">
                    {file.name}
                  </span>
                  {outcome.reason !== undefined && (
                    <span className="mt-0.5 block text-rose-700">
                      {outcome.reason}
                    </span>
                  )}
                </span>
                <span className={DATA_CLASS + " shrink-0 text-slate-500"}>
                  {formatBytes(file.size)}
                </span>
                <span
                  className={
                    "w-14 shrink-0 text-right " + OUTCOME_CLASS[outcome.state]
                  }
                >
                  {OUTCOME_LABEL[outcome.state]}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
