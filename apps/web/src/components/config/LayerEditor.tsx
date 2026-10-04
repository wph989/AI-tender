"use client";

/**
 * 单层配置编辑器：本地草稿 → 补丁 → 创建版本（设计文档 08 第 2 节）。
 *
 * L1 保存即生效；L2/L3 保存后是草稿，要等影响清单逐条确认后才能激活——
 * 这个差异由后端 status 决定，前端只负责把结果说清楚（"已生效" vs "已生成草稿"）。
 */

import { useState } from "react";

import { BUTTON_CLASS, INPUT_CLASS, PRIMARY_BUTTON_CLASS, SELECT_CLASS } from "@/components/ui";
import { createRelease } from "@/lib/api/config";
import { LAYER_HINTS, LAYER_LABELS, buildPatch, formatValue } from "@/lib/config/draft";
import { message } from "@/lib/errors";
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

  if (items.length === 0) return null;
  const writable = items.every((item) => item.writable);

  const draftCount = items.filter(
    (item) => item.key in drafts && drafts[item.key] !== formatValue(item.value),
  ).length;

  const save = async () => {
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
      const result = await createRelease({ values: patch, note: note || undefined });
      setDrafts({});
      setNote("");
      await onSaved(
        result.status === "active"
          ? "已保存并立即生效（L1 不需要回归门禁）"
          : "已生成草稿 v" + result.version_no + "，请到「版本与发布」逐条确认影响后激活",
      );
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
          <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">{LAYER_LABELS[layer]}</h2>
          <p className="mt-1 text-[13px] leading-5 text-slate-500">{LAYER_HINTS[layer]}</p>
        </div>
        <span className="text-[13px] text-slate-400">{items.length} 项</span>
      </div>

      {!writable && (
        <p className="mt-3 border border-amber-200 bg-amber-50 px-2 py-1 text-[13px] text-amber-800">
          当前角色只读该层，写操作会被服务端拒绝。
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
                  <code className="text-[13px] text-slate-700">{item.key}</code>
                  {item.overridden && (
                    <span className="rounded-lg bg-sky-50 px-1 text-[11px] text-sky-700">
                      已覆盖默认值
                    </span>
                  )}
                  {changed && (
                    <span className="rounded-lg bg-amber-50 px-1 text-[11px] text-amber-700">
                      未保存
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[13px] text-slate-500">{item.description}</p>
              </div>
              {item.value_type === "bool" ? (
                <select
                  aria-label={item.description || item.key}
                  className={SELECT_CLASS + " w-full"}
                  value={value}
                  disabled={!writable}
                  onChange={(event) =>
                    setDrafts((current) => ({ ...current, [item.key]: event.target.value }))
                  }
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : (
                <input
                  className={
                    INPUT_CLASS + " w-full" + (item.value_type === "secret" ? " font-mono" : "")
                  }
                  aria-label={item.description || item.key}
                  type={
                    item.value_type === "int" || item.value_type === "number" ? "number" : "text"
                  }
                  value={value}
                  disabled={!writable}
                  onChange={(event) =>
                    setDrafts((current) => ({ ...current, [item.key]: event.target.value }))
                  }
                />
              )}
              <span className="config-field-default text-[11px] text-slate-400">
                默认 {formatValue(item.default)}
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

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          aria-label="配置变更说明"
          className={INPUT_CLASS + " min-w-0 flex-1"}
          placeholder="变更说明（会写进审计，例如：调整保证金字段提示词）"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <button
          type="button"
          className={PRIMARY_BUTTON_CLASS}
          disabled={!writable || busy || draftCount === 0}
          onClick={() => void save()}
        >
          {layer === "L1" ? "保存并立即生效" : "保存为草稿"}
        </button>
        <button
          type="button"
          className={BUTTON_CLASS}
          disabled={busy || draftCount === 0}
          onClick={() => {
            setDrafts({});
            setError(null);
          }}
        >
          放弃修改
        </button>
      </div>
    </section>
  );
}
