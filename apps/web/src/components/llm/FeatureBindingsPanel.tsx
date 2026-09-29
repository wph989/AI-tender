"use client";

/**
 * 功能绑定面板：给功能选模型、排优先级、改转移深度（设计文档 12 第 3、4、8 节）。
 *
 * 优先级是"整表"的：草稿就是一份有序的模型行 id 数组，任何排序动作都只改这份数组，
 * 保存时整表 PUT（服务端按位置写 1..N）。单行改数字会造出空洞与同级，接口也不接受。
 */

import { useState } from "react";

import { replaceBindings, updateFeature } from "@/lib/api/llm";
import { message } from "@/lib/llm/format";
import { MAX_BINDINGS, moveToPriority } from "@/lib/llm/priority";
import type { LlmFeature, LlmModel } from "@/types/llm";

import { BUTTON_CLASS, DANGER_BUTTON_CLASS, INPUT_CLASS, PRIMARY_BUTTON_CLASS } from "./ui";

interface Props {
  features: LlmFeature[];
  models: LlmModel[];
  onChanged: () => Promise<void>;
}

interface Draft {
  key: string;
  ids: number[];
  limit: number;
}

export function FeatureBindingsPanel({ features, models, onChanged }: Props) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pendingAdd, setPendingAdd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = features.find((feature) => feature.key === activeKey) ?? features[0];
  if (active === undefined) {
    return (
      <section className="rounded border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">功能绑定</h2>
        <p className="mt-3 text-sm text-slate-500">后端没有返回功能列表。</p>
      </section>
    );
  }

  const serverIds = active.bindings.map((binding) => binding.model_row_id);
  // 草稿只对当前功能有效：切功能就丢掉，避免把 A 的排序带到 B 上
  const ids = draft !== null && draft.key === active.key ? draft.ids : serverIds;
  const limit =
    draft !== null && draft.key === active.key ? draft.limit : active.failover_limit;
  const dirty = ids.join(",") !== serverIds.join(",") || limit !== active.failover_limit;

  const update = (nextIds: number[], nextLimit: number = limit) =>
    setDraft({ key: active.key, ids: nextIds, limit: Math.min(Math.max(nextLimit, 1), 10) });

  const run = async (fallback: string, task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (caught) {
      setError(message(caught, fallback));
    } finally {
      setBusy(false);
    }
  };

  const save = () =>
    void run("保存绑定失败", async () => {
      // 先写绑定再写深度：绑定失败时不要留下一个只改了深度的半成品配置
      await replaceBindings(active.key, ids);
      await updateFeature(active.key, limit);
      setDraft(null);
      await onChanged();
    });

  const modelById = new Map(models.map((model) => [model.id, model]));
  const unbound = models.filter((model) => !ids.includes(model.id));
  const effective = ids.length === 0 ? 0 : Math.max(1, Math.min(limit, ids.length));

  const setPriority = (modelRowId: number, target: number) => {
    update(moveToPriority(ids, modelRowId, target));
  };

  const shift = (index: number, delta: number) => {
    const modelRowId = ids[index];
    if (modelRowId === undefined) return;
    update(moveToPriority(ids, modelRowId, index + 1 + delta));
  };

  const add = () => {
    const modelRowId = Number(pendingAdd);
    if (!Number.isSafeInteger(modelRowId) || modelRowId <= 0) return;
    if (ids.includes(modelRowId) || ids.length >= MAX_BINDINGS) return;
    update([...ids, modelRowId]);
    setPendingAdd("");
  };

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">功能绑定</h2>
          <p className="mt-1 text-xs text-slate-500">
            1 级为首选模型，失败后按 2、3… 降级；同一模型不会原地重试。
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          转移深度
          <input
            type="number"
            min={1}
            max={10}
            className={INPUT_CLASS + " w-20"}
            value={limit}
            onChange={(event) => update(ids, Number(event.target.value))}
          />
          级
        </div>
      </div>

      <div className="mt-3 flex gap-1">
        {features.map((feature) => (
          <button
            key={feature.key}
            type="button"
            onClick={() => {
              setActiveKey(feature.key);
              setDraft(null);
              setError(null);
            }}
            className={
              feature.key === active.key
                ? "rounded bg-slate-900 px-3 py-1 text-xs text-white"
                : "rounded border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50"
            }
          >
            {feature.name}
            <span className="ml-1 text-slate-400">{feature.bindings.length}</span>
          </button>
        ))}
      </div>

      {error !== null && (
        <p className="mt-3 rounded bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>
      )}

      <p className="mt-3 text-xs text-slate-500">
        共 {ids.length} 个候选，实际前 {effective} 级生效（深度会夹到候选数量以内）。
      </p>

      {ids.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">
          这个功能还没有绑定模型，抽取会整体回退到 .env 的单模型配置。
        </p>
      ) : (
        <table className="mt-2 w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="py-1 pr-3 font-normal w-16">级别</th>
              <th className="py-1 pr-3 font-normal">模型</th>
              <th className="py-1 pr-3 font-normal">供应商</th>
              <th className="py-1 pr-3 font-normal">状态</th>
              <th className="py-1 text-right font-normal">调整</th>
            </tr>
          </thead>
          <tbody>
            {ids.map((modelRowId, index) => {
              const model = modelById.get(modelRowId);
              return (
                <tr key={modelRowId} className="border-t border-slate-100">
                  <td className="py-2 pr-3">
                    <input
                      type="number"
                      min={1}
                      max={ids.length}
                      className={INPUT_CLASS + " w-16"}
                      value={index + 1}
                      onChange={(event) => setPriority(modelRowId, Number(event.target.value))}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <div className="font-medium text-slate-800">
                      {model?.display_name ?? "模型 #" + modelRowId}
                    </div>
                    <div className="text-xs text-slate-500">{model?.model_id ?? "已不在模型列表中"}</div>
                  </td>
                  <td className="py-2 pr-3 text-xs text-slate-600">
                    {model?.provider_name ?? "—"}
                  </td>
                  <td className="py-2 pr-3 text-xs">
                    {model === undefined ? (
                      "—"
                    ) : model.enabled ? (
                      <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">
                        启用
                      </span>
                    ) : (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-500">
                        停用
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-right whitespace-nowrap">
                    <button
                      type="button"
                      className={BUTTON_CLASS + " mr-1"}
                      disabled={index === 0}
                      onClick={() => shift(index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className={BUTTON_CLASS + " mr-1"}
                      disabled={index === ids.length - 1}
                      onClick={() => shift(index, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className={DANGER_BUTTON_CLASS}
                      onClick={() => update(ids.filter((id) => id !== modelRowId))}
                    >
                      移除
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          className={INPUT_CLASS}
          value={pendingAdd}
          onChange={(event) => setPendingAdd(event.target.value)}
        >
          <option value="">选择要加入的模型…</option>
          {unbound.map((model) => (
            <option key={model.id} value={model.id}>
              {model.display_name}
              {model.enabled ? "" : "（停用）"} · {model.provider_name ?? "—"}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={BUTTON_CLASS}
          disabled={pendingAdd === "" || ids.length >= MAX_BINDINGS}
          onClick={add}
        >
          加到最低级
        </button>
        <span className="text-xs text-slate-400">最多 {MAX_BINDINGS} 个</span>

        <div className="ml-auto flex gap-2">
          <button
            type="button"
            className={PRIMARY_BUTTON_CLASS}
            disabled={busy || !dirty}
            onClick={save}
          >
            保存
          </button>
          <button
            type="button"
            className={BUTTON_CLASS}
            disabled={busy || !dirty}
            onClick={() => setDraft(null)}
          >
            放弃改动
          </button>
        </div>
      </div>
    </section>
  );
}