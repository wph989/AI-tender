"use client";

/**
 * 交件台：把文件放到台面上，而不是「点这里选择文件」。
 *
 * 为什么不做常见的虚线圆角框 + 云朵图标：那套外观把「上传」画成了一件抽象的事，
 * 而这里要同时说清三件事——拖进来、能选哪些格式、上传后会跑什么流水线。
 * 一条实底横带 + 左侧荧光黄竖线（和导航字标、列表行是同一道卷宗脊）把注意力
 * 引到「操作」上，格式与限制写在右边，读者顺序是从左到右：先做什么，做完会怎样。
 *
 * ZIP 单独走 archive 字段：后端会解压后逐个入库（见 api/project_files.py 的
 * _read_archive），混在 files 里只会被当成一个不参与解析的文件。
 */

import { useRef, useState } from "react";

import {
  BUTTON_CLASS,
  DATA_CLASS,
  PRIMARY_BUTTON_CLASS,
  SELECT_CLASS,
} from "@/components/ui";
import { formatBytes } from "@/lib/format";
import { FILE_ROLE_LABELS, type FileRole, type ParseTier } from "@/types/projects";

const ACCEPT =
  ".pdf,.doc,.docx,.odt,.rtf,.ppt,.pptx,.odp,.xls,.xlsx,.xlsm,.ods,.dwg,.dxf,.vsd,.vsdx,.zip";

const FORMATS = ["PDF", "Word", "PPT", "Excel", "CAD", "ZIP"];

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

interface Props {
  busy: boolean;
  onUpload: (files: File[], archive: File | null, options: UploadOptionsState) => Promise<void>;
}

export function UploadPanel({ busy, onUpload }: Props) {
  const [staged, setStaged] = useState<File[]>([]);
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
  };

  const submit = async () => {
    if (staged.length === 0 || busy) return;
    const archive = staged.find((file) => file.name.toLowerCase().endsWith(".zip")) ?? null;
    const files = staged.filter((file) => file !== archive);
    await onUpload(files, archive, options);
    setStaged([]);
    if (inputRef.current) inputRef.current.value = "";
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
        className={"flex items-stretch " + (dragging ? "bg-amber-50" : "bg-white")}
      >
        <div aria-hidden className={"w-[4px] shrink-0 " + (dragging ? "bg-amber-500" : "bg-amber-400")} />
        <div
          className={
            "flex flex-1 flex-wrap items-center gap-x-6 gap-y-4 px-5 py-5 " +
            (dragging ? "outline-2 -outline-offset-2 outline-dashed outline-amber-400" : "")
          }
        >
          <div className="min-w-0 flex-1">
            <p className="text-[11px] tracking-[0.18em] text-slate-400 uppercase">交件台</p>
            <p className="mt-1.5 font-serif text-[19px] leading-7 text-slate-900">
              {dragging ? "松手即入库" : "把招标文件拖到这里"}
            </p>
            <p className="mt-1.5 text-[13px] leading-5 text-slate-500">
              ZIP 会自动解开；清单与图纸按角色归档、不参与文本解析。单次最多 100 个文件，
              合计不超过 1 GiB。
            </p>
            <ul className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {FORMATS.map((format) => (
                <li
                  key={format}
                  className={DATA_CLASS + " border border-slate-200 px-1.5 py-[1px] text-[11px] text-slate-500"}
                >
                  {format}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex items-center gap-2">
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
        <ul className="border-t border-slate-200">
          {staged.map((file) => (
            <li
              key={file.name + file.size}
              className="flex items-center gap-3 border-b border-slate-100 px-5 py-1.5 text-[13px] last:border-b-0"
            >
              <span className="min-w-0 flex-1 truncate text-slate-700">{file.name}</span>
              <span className={DATA_CLASS + " text-slate-500"}>{formatBytes(file.size)}</span>
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
      )}
    </section>
  );
}
