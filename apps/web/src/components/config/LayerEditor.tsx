"use client";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { useFeedback } from "@/hooks/useFeedback";
import { Button, Input, Select } from "antd";

/**
 * 单层配置编辑器：本地草稿 → 补丁 → 创建版本（docs/质量/08-动态配置中心.md）。
 *
 * L1 保存即生效；L2 保存后是草稿，要等影响清单逐条确认后才能激活——
 * 这个差异由后端 status 决定，前端只负责把结果说清楚（"已生效" vs "已生成草稿"）。
 */

import { useState } from "react";

import { createRelease } from "@/lib/api/config";
import {
  LAYER_HINTS,
  LAYER_LABELS,
  buildPatch,
  formatValue,
} from "@/lib/config/draft";
import { message } from "@/lib/errors";
import { configChoiceLabel, configHint, configLabel, configValueLabel } from "@/lib/config/presentation";
import type { ConfigItem, ConfigLayer } from "@/types/config";

interface Props {
  layer: ConfigLayer;
  items: ConfigItem[];
  onSaved: (text: string) => Promise<void> | void;
}

export function LayerEditor({ layer, items, onSaved }: Props) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useFeedback(error);

  const writable = items.some((item) => item.writable);

  const draftCount = items.filter(
    (item) =>
      item.key in drafts && drafts[item.key] !== formatValue(item.value),
  ).length;

  useUnsavedChanges(draftCount > 0, busy);
  if (items.length === 0) return null;

  const save = async () => {
    if (busy) return;
    const { patch, errors } = buildPatch(items, drafts);
    if (errors.length > 0) {
      setError(errors.join("；"));
      return;
    }
    if (Object.keys(patch).length === 0) {
      setError("没有需要修改的配置项");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await createRelease({
        values: patch,
        note: note || undefined,
      });
      setDrafts({});
      setNote("");
      await Promise.resolve(
        onSaved(
          result.status === "active"
            ? "配置已保存。各项设置按上方说明生效。"
            : "已生成草稿 v" +
                result.version_no +
                "，请到「版本与发布」确认变更影响后发布",
        ),
      ).catch(() => setError("配置已保存，但刷新失败，请刷新页面查看版本。"));
    } catch (caught) {
      setError(message(caught, "保存配置失败"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">
            {LAYER_LABELS[layer]}
          </h2>
          <p className="mt-1 text-[13px] leading-5 text-slate-500">
            {LAYER_HINTS[layer]}
          </p>
        </div>
        <span className="text-[13px] text-slate-400">{items.length} 项</span>
      </div>

      {!writable && (
        <p className="mt-3 border border-amber-200 bg-amber-50 px-2 py-1 text-[13px] text-amber-800">
          当前没有可修改项，原因见各项说明。
        </p>
      )}

      <div className="mt-3 flex flex-col divide-y divide-slate-100">
        {items.map((item) => {
          const value = drafts[item.key] ?? formatValue(item.value);
          const changed = value !== formatValue(item.value);
          return (
            <div key={item.key} className="config-field">
              <div className="config-field-label">
                <div className="flex items-center gap-2">
                  <strong className="text-[13px] font-medium text-slate-700">{configLabel(item.key, item.description)}</strong>
                  {item.overridden && (
                    <span className="rounded-lg bg-sky-50 px-1 text-[11px] text-sky-700">
                      已自定义
                    </span>
                  )}
                  {changed && (
                    <span className="rounded-lg bg-amber-50 px-1 text-[11px] text-amber-700">
                      未保存
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[13px] text-slate-500">
                  {configHint(item.key)}
                </p>
                <details className="mt-1 text-xs text-slate-400">
                  <summary className="w-fit cursor-pointer">参数详情</summary>
                  <code className="block break-all pt-1">{item.key}</code>
                  <p className="mt-1">{item.description}</p>
                </details>
                {item.key === "analysis.context_tokens" && Number(value) < 4096 && (
                  <p className="mt-1 text-xs text-amber-700">
                    固定指令和工具说明也占用上下文，较小预算可能无法容纳完整任务。
                  </p>
                )}
              </div>
              {item.value_type === "bool" ? (
                <Select<string>
                  aria-label={configLabel(item.key, item.description)}
                  className={" w-full"}
                  value={String(value)}
                  disabled={!item.writable || busy}
                  onChange={(selectedValue) =>
                    setDrafts((current) => ({
                      ...current,
                      [item.key]: selectedValue,
                    }))
                  }
                >
                  <Select.Option value="true">开启</Select.Option>
                  <Select.Option value="false">关闭</Select.Option>
                </Select>
              ) : item.choices ? (
                <Select<string>
                  aria-label={configLabel(item.key, item.description)}
                  className="w-full"
                  value={value}
                  disabled={!item.writable || busy}
                  options={item.choices.map((choice) => ({ value: choice, label: configChoiceLabel(item.key, choice) }))}
                  onChange={(selectedValue) => setDrafts((current) => ({
                    ...current, [item.key]: selectedValue,
                  }))}
                />
              ) : (
                <Input
                  className={
                    "" +
                    " w-full" +
                    (item.value_type === "secret" ? " font-mono" : "")
                  }
                  aria-label={configLabel(item.key, item.description)}
                  type={
                    item.value_type === "int" || item.value_type === "number"
                      ? "number"
                      : "text"
                  }
                  value={value}
                  min={item.minimum}
                  max={item.maximum}
                  step={item.value_type === "number" ? "any" : 1}
                  disabled={!item.writable || busy}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [item.key]: event.target.value,
                    }))
                  }
                />
              )}
              <span className="config-field-default text-[11px] text-slate-400">
                默认 {configValueLabel(item.key, item.default)}
              </span>
            </div>
          );
        })}
      </div>

      {error !== null && (
        <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-700">
          {error}
        </p>
      )}

      <div className="sticky-actions mt-3 flex flex-wrap items-center gap-2">
        <Input
          aria-label="配置变更说明"
          className={" min-w-0 flex-1"}
          placeholder="变更说明（可选，例如：延长分析等待时间）"
          disabled={busy}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <Button
          type="primary"
          htmlType="button"

          disabled={!writable || busy || draftCount === 0}
          onClick={() => void save()}
        >
          {busy
            ? "正在保存…"
            : layer === "L1"
              ? "保存并立即生效"
              : "保存为草稿"}
        </Button>
        <Button
          htmlType="button"

          disabled={busy || draftCount === 0}
          onClick={() => {
            setDrafts({});
            setNote("");
            setError(null);
          }}
        >
          放弃修改
        </Button>
      </div>
    </section>
  );
}
