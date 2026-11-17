"use client";

import { Alert, App, Button, Checkbox, Form, Input, Modal, Select, Upload } from "antd";
import { useState } from "react";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { patchProjectFile, replaceProjectFile } from "@/lib/api/client";
import { OCR_MODES, PARSE_TIERS } from "@/lib/projects/parseOptions";
import type { WireProjectFile, OcrMode, ParseTier } from "@/types/projects";

/** 与后端末尾扩展名的判断保持一致，排除仅有开头的点或结尾的点。 */
function fileExtension(name: string) {
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot) : "";
}

/** 换版沿用旧文件解析选项，让用户确认新内容后再创建新版本。 */
export function FileEditModal({ projectId, file, mode, onClose, onSaved }: {
  projectId: number; file: WireProjectFile; mode: "rename" | "replace";
  onClose: () => void; onSaved: () => Promise<unknown>;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replacement, setReplacement] = useState<File | null>(null);
  const close = useUnsavedChanges(dirty, busy);
  // 显示名称也决定换版和转换的格式；只开放名称主体，避免重命名改变处理路径。
  const extension = fileExtension(file.display_name);
  const stem = extension ? file.display_name.slice(0, -extension.length) : file.display_name;
  const maxNameLength = 500 - extension.length;
  return <Modal open title={mode === "rename" ? "重命名文件" : "上传新版本"}
    className="editor-modal" centered mask={{ closable: false }} closable={!busy} keyboard={!busy}
    onCancel={() => close(onClose)} okText="保存" confirmLoading={busy}
    okButtonProps={{ htmlType: "submit", form: "edit-file" }} cancelButtonProps={{ disabled: busy }}>
    <p className="mb-4 break-all text-slate-600">{file.display_name}</p>
    {error && <Alert type="error" showIcon title={error} className="mb-4" />}
    <Form id="edit-file" layout="vertical" disabled={busy}
      initialValues={{ name: stem, autoParse: file.is_parseable,
        tier: file.parse_tier ?? "standard", ocrMode: file.parse_ocr_mode ?? "auto" }}
      onValuesChange={() => setDirty(true)}
      onFinish={async (values: { name: string; autoParse: boolean; tier: ParseTier; ocrMode: OcrMode }) => {
        if (busy) return;
        if (mode === "replace" && !replacement) { setError("请先选择新版本文件"); return; }
        setBusy(true); setError(null);
        try {
          if (mode === "rename") await patchProjectFile(projectId, file.project_file_id, { display_name: values.name.trim() + extension });
          else await replaceProjectFile(projectId, file.project_file_id, replacement!, values);
          setDirty(false);
          void message.success(mode === "rename" ? "文件已重命名" : "新版本已上传");
          await onSaved().catch(() => { void message.warning("保存成功，列表刷新失败，请刷新页面"); });
          onClose();
        } catch (caught) { setError(caught instanceof Error ? caught.message : "保存失败，请重试"); }
        finally { setBusy(false); }
      }}>
      {mode === "rename" ? <Form.Item label="文件名称" name="name" rules={[
        { required: true, whitespace: true, message: "请输入文件名称" },
        { max: maxNameLength, message: `文件名称最多${maxNameLength}字（扩展名另行保留）` },
        {
          validator: (_, value: string) => {
            // 无扩展名的归档文件也要保持原格式，不能通过重命名伪装成可解析文件。
            if (!extension && fileExtension(value?.trim() ?? ""))
              return Promise.reject(new Error("原文件没有扩展名，名称中不能新增扩展名"));
            return Promise.resolve();
          },
        },
      ]}><Input autoFocus maxLength={maxNameLength} suffix={extension || undefined} /></Form.Item> : <>
        <Alert className="mb-4" type="info" title="旧版文件和既有报告保留，新分析使用新版本。" />
        <Form.Item label="新版本文件" required>
          <Upload maxCount={1} disabled={busy} accept={extension || undefined}
            fileList={replacement ? [{ uid: "replacement", name: replacement.name }] : []}
            beforeUpload={(next) => {
              if (next.size > 512 * 1024 * 1024) { setError("单个文件不能超过512 MiB"); return Upload.LIST_IGNORE; }
              // accept 只过滤选择框；拖入文件也必须校验，当前换版接口沿用旧文件格式。
              if (fileExtension(next.name).toLowerCase() !== extension.toLowerCase()) {
                setReplacement(null);
                setError(extension
                  ? `新版本须使用 ${extension.toLowerCase()} 格式，请重新选择文件`
                  : "新版本文件不能带扩展名，请重新选择文件");
                return Upload.LIST_IGNORE;
              }
              setReplacement(next); setDirty(true); setError(null); return false;
            }} onRemove={() => { setReplacement(null); setDirty(true); }}>
            <Button>选择文件</Button>
          </Upload>
        </Form.Item>
        <Form.Item name="autoParse" valuePropName="checked"><Checkbox>上传后自动解析</Checkbox></Form.Item>
        <Form.Item label="解析档位" name="tier"><Select options={PARSE_TIERS} /></Form.Item>
        <Form.Item label="文字识别" name="ocrMode"><Select options={OCR_MODES} /></Form.Item>
      </>}
    </Form>
  </Modal>;
}
