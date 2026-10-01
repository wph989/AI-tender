"use client";

/**
 * 交件台：把文件放到台面上，而不是「点这里选择文件」。
 *
 * 为什么不做常见的虚线圆角框 + 云朵图标：那套外观把「上传」画成了一件抽象的事，
 * 而这里要同时说清三件事——拖进来、能选哪些格式、上传后会跑什么流水线。
 * 一条实底横带 + 左侧荧光黄竖线（和导航字标、列表行是同一道卷宗脊）把注意力
 * 引到「操作」上，右侧一栏专门写规格与角色推断规则：用户最常问的两个问题就是
 * 「能传多大」和「为什么这个 Excel 不算解析文件」。
 *
 * 为什么拖拽区给到 200px 以上：这块区域越矮，越像页面上一条不起眼的附件输入框；
 * 它是这一页的主操作，必须一眼看出「东西放这里」。
 *
 * ZIP 单独走 archive 字段：后端会解压后逐个入库（见 api/project_files.py 的
 * _read_archive），混在 files 里只会被当成一个不参与解析的文件。
 *
 * 为什么要有逐文件结果：一次请求只回一个汇总，而用户看的是自己挑的那几个文件。
 * 上传结束后每一行都标出「已入库 / 被拒（原因）/ 未入库」，不必去页面顶部对名字。
 */

import { useRef, useState } from "react";

import {
  BUTTON_CLASS,
  DATA_CLASS,
  EYEBROW_CLASS,
  PRIMARY_BUTTON_CLASS,
  SELECT_CLASS,
} from "@/components/ui";
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

const FORMATS = ["PDF", "Word", "PPT", "Excel", "CAD", "ZIP"];

/**
 * 上限口径与后端 project_files.py 的常量一一对应（_MAX_UPLOAD_BYTES 等）。
 * 两处不一致的后果是用户先撞墙、再被告知限制，所以这里写的是服务端的真实数字。
 */
const LIMITS = [
  "单个文件 ≤ 512 MiB",
  "单次合计 ≤ 1 GiB，最多 100 个文件",
  "ZIP ≤ 128 MiB，成员 ≤ 500 个、解压后 ≤ 512 MiB",
];

const ROLE_RULE =
  "角色按扩展名推断：xls / xlsx / xlsm / ods → 清单，dwg / dxf / vsd / vsdx → 图纸，";

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
  const [staged, setStaged] = useState<File[]>([]);
  const [batch, setBatch] = useState<BatchRow[] | null>(null);
  const [ratio, setRatio] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [options, setOptions] = useState<UploadOptionsState>({
    tier: "standard",
    ocrMode: "auto",
    autoParse: true,
    role: "",
  });
  const inputRef = useRef<HTMLInputElement>(null);

  const stage = (incoming: FileList | null) => {
    if (incoming === null) return;
    // 同名同大小视为同一个文件：拖两次同一份标书是常事，去重比报错友好。
    const next = [...staged];
    for (const file of Array.from(incoming)) {
      if (!next.some((item) => item.name === file.name && item.size === file.size)) {
        next.push(file);
      }
    }
    setStaged(next);
    setBatch(null);
  };

  const reset = () => {
    setBatch(null);
    setStaged([]);
    setRatio(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const submit = async () => {
    if (staged.length === 0 || busy) return;
    const pending = staged;
    const archive = pending.find((file) => file.name.toLowerCase().endsWith(".zip")) ?? null;
    const files = pending.filter((file) => file !== archive);
    setRatio(0);
    try {
      const result = await onUpload(files, archive, options, setRatio);
      setBatch(pending.map((file) => ({ file, outcome: outcomeOf(file.name, result) })));
      setStaged([]);
      if (inputRef.current) inputRef.current.value = "";
    } catch (caught: unknown) {
      // 整批都没入库时后端仍会回逐文件原因，摊回每一行；其余错误由页面顶部的横幅承接。
      if (caught instanceof UploadRejectedError) {
        const rejected: UploadResult = { added: [], jobs: [], skipped: caught.skipped };
        setBatch(pending.map((file) => ({ file, outcome: outcomeOf(file.name, rejected) })));
        setStaged([]);
        if (inputRef.current) inputRef.current.value = "";
      }
    } finally {
      setRatio(null);
    }
  };

  return (
    <section className="border border-slate-300 bg-white">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          stage(event.dataTransfer.files);
        }}
        className={"flex min-h-[208px] items-stretch " + (dragging ? "bg-amber-50" : "bg-white")}
      >
        <div
          aria-hidden
          className={"w-[4px] shrink-0 " + (dragging ? "bg-amber-500" : "bg-amber-400")}
        />
        <div
          className={
            "flex flex-1 flex-col gap-y-5 px-6 py-6 lg:flex-row lg:gap-x-10 " +
            (dragging ? "outline-2 -outline-offset-2 outline-dashed outline-amber-400" : "")
          }
        >
          <div className="min-w-0 flex-1">
            <p className={EYEBROW_CLASS}>01 · 交件台</p>
            <p className="mt-2 font-serif text-[22px] leading-8 text-slate-900">
              {dragging ? "松手即入库" : "把招标文件拖到这里"}
            </p>
            <p className="mt-2 max-w-xl text-[13px] leading-5 text-slate-500">
              ZIP 会自动解开、按成员逐个入库。只有 PDF 与 Word / PPT 会进入「转换 → 解析 → 抽取」这条
              流水线；清单与图纸入库备查，不参与文本解析。
            </p>
            <ul className="mt-3 flex flex-wrap items-center gap-1.5">
              {FORMATS.map((format) => (
                <li
                  key={format}
                  className={
                    DATA_CLASS + " border border-slate-200 px-1.5 py-[1px] text-[11px] text-slate-500"
                  }
                >
                  {format}
                </li>
              ))}
            </ul>
          </div>

          {/*
           * 右栏专门放「规则」：能传多大、ZIP 怎么算、角色怎么推断。
           * 这些不是帮助文档——它们决定用户下一步怎么做，放在动作旁边才算说清楚。
           */}
          <div className="w-full shrink-0 lg:w-[23rem]">
            <p className={EYEBROW_CLASS}>规格与角色</p>
            <dl className="mt-2 flex flex-col gap-1.5 text-[13px] leading-5">
              {LIMITS.map((line) => (
                <dd key={line} className="flex gap-2 text-slate-500">
                  <span aria-hidden className="mt-[7px] h-[4px] w-[4px] shrink-0 bg-slate-400" />
                  <span>{line}</span>
                </dd>
              ))}
            </dl>
            <p className="mt-2 text-[13px] leading-5 text-slate-500">
              {ROLE_RULE}其余 → 主文件。上传后可在文件清单里逐个改角色。
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <input
                ref={inputRef}
                type="file"
                multiple
                accept={ACCEPT}
                className="hidden"
                onChange={(event) => stage(event.target.files)}
              />
              <button type="button" className={BUTTON_CLASS} onClick={() => inputRef.current?.click()}>
                选择文件
              </button>
              <button
                type="button"
                className={PRIMARY_BUTTON_CLASS}
                disabled={staged.length === 0 || busy}
                onClick={() => void submit()}
              >
                {busy ? "正在上传…" : staged.length > 0 ? `上传 ${staged.length} 个文件` : "上传文件"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 参数行：这些值只在「入库」这一刻有效，所以跟在上传动作下面，而不是单独一页设置。 */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-slate-200 bg-slate-50 px-5 py-2.5 text-[13px] text-slate-600">
        <label className="flex items-center gap-2">
          解析档位
          <select
            value={options.tier}
            onChange={(event) => setOptions({ ...options, tier: event.target.value as ParseTier })}
            className={SELECT_CLASS + " py-1"}
          >
            {TIER_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          OCR
          <select
            value={options.ocrMode}
            onChange={(event) =>
              setOptions({ ...options, ocrMode: event.target.value as "auto" | "txt" | "ocr" })
            }
            className={SELECT_CLASS + " py-1"}
          >
            <option value="auto">auto · 自动判断</option>
            <option value="txt">txt · 强制文本层</option>
            <option value="ocr">ocr · 强制 OCR</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          角色
          <select
            value={options.role}
            onChange={(event) =>
              setOptions({ ...options, role: event.target.value as FileRole | "" })
            }
            className={SELECT_CLASS + " py-1"}
          >
            <option value="">按扩展名自动判断</option>
            {(Object.keys(FILE_ROLE_LABELS) as FileRole[]).map((role) => (
              <option key={role} value={role}>
                {FILE_ROLE_LABELS[role]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={options.autoParse}
            onChange={(event) => setOptions({ ...options, autoParse: event.target.checked })}
          />
          上传后自动解析
        </label>
      </div>

      {staged.length > 0 && (
        <div className="border-t border-slate-200">
          {ratio !== null && (
            <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 bg-slate-50 px-5 py-2 text-[13px] text-slate-600">
              <span>正在上传</span>
              <progress
                className="h-1.5 w-48"
                value={ratio}
                max={1}
                aria-label="上传进度"
              />
              <span className={DATA_CLASS}>{Math.round(ratio * 100)}%</span>
              {/* 进度条只走到「字节发完」为止；入库、建版本、派任务都在服务端，还要等一会儿 */}
              <span className="text-slate-400">传完还要在服务端逐个入库，请稍等</span>
            </div>
          )}
          <ul>
            {staged.map((file) => (
              <li
                key={file.name + "|" + file.size}
                className="flex items-center gap-3 border-b border-slate-100 px-5 py-1.5 text-[13px] last:border-b-0"
              >
                <span className="min-w-0 flex-1 truncate text-slate-700">{file.name}</span>
                <span className={DATA_CLASS + " text-slate-500"}>{formatBytes(file.size)}</span>
                <span className="w-16 text-right text-slate-400">
                  {ratio === null ? "待上传" : "上传中"}
                </span>
                <button
                  type="button"
                  className="text-slate-400 hover:text-rose-600"
                  aria-label={"移除 " + file.name}
                  onClick={() => setStaged(staged.filter((item) => item !== file))}
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
              入库 {batch.filter((row) => row.outcome.state === "added").length} 个，
              未入库 {batch.filter((row) => row.outcome.state !== "added").length} 个
            </span>
            <button type="button" className="ml-auto text-slate-500 hover:text-slate-900" onClick={reset}>
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
                  <span className="block truncate text-slate-700">{file.name}</span>
                  {outcome.reason !== undefined && (
                    <span className="mt-0.5 block text-rose-700">{outcome.reason}</span>
                  )}
                </span>
                <span className={DATA_CLASS + " shrink-0 text-slate-500"}>{formatBytes(file.size)}</span>
                <span className={"w-14 shrink-0 text-right " + OUTCOME_CLASS[outcome.state]}>
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
