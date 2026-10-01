"use client";

/**
 * 模型面板：供应商下的具体模型与推理参数（设计文档 12 第 2、8 节）。
 *
 * 参数留空表示"不传"而不是 0：temperature / max_tokens 为空时后端用网关默认值，
 * 填 0 会被当成真实参数发出去。改参数用 PATCH，只发改动过的项。
 */

import { Fragment, useState } from "react";

import { createModel, deleteModel, testModel, updateModel } from "@/lib/api/llm";
import { formatTime, message, testLabel } from "@/lib/llm/format";
import type {
  LlmModel,
  LlmProvider,
  LlmTestResult,
  ModelInput,
  ModelPatchInput,
} from "@/types/llm";

import {
  BUTTON_CLASS,
  DANGER_BUTTON_CLASS,
  FORM_LABEL_CLASS,
  FORM_ROW_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SELECT_CLASS,
} from "./ui";

interface Props {
  providers: LlmProvider[];
  models: LlmModel[];
  onChanged: () => Promise<void>;
}

/** 空串按"不改/不传"处理；JSON.stringify 会丢掉 undefined，正好是后端要的语义。 */
function optionalNumber(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (trimmed === "") return undefined;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : undefined;
}

export function ModelsPanel({ providers, models, onChanged }: Props) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<number, LlmTestResult>>({});

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

  const save = (model: LlmModel | null, input: ModelInput | ModelPatchInput) =>
    void run(model === null ? "新建模型失败" : "保存模型失败", async () => {
      if (model === null) await createModel(input as ModelInput);
      else await updateModel(model.id, input);
      setEditing(null);
      await onChanged();
    });

  const remove = (model: LlmModel) => {
    if (!window.confirm("删除模型「" + model.display_name + "」？仍被功能绑定时会被拒绝。")) {
      return;
    }
    void run("删除模型失败", async () => {
      await deleteModel(model.id);
      await onChanged();
    });
  };

  const test = (model: LlmModel) =>
    void run("测试模型失败", async () => {
      const result = await testModel(model.id);
      setResults((previous) => ({ ...previous, [model.id]: result }));
      await onChanged();
    });

  const newForm = editing === "new" && (
    <div className="mt-3">
      <ModelForm
        providers={providers}
        model={null}
        busy={busy}
        onSubmit={(input) => save(null, input)}
        onCancel={() => setEditing(null)}
      />
    </div>
  );

  return (
    <section className="border border-slate-200 bg-white px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-serif text-[19px] leading-[28px] text-slate-900">模型</h2>
          <p className="mt-1 text-[13px] leading-5 text-slate-500">
            超时、温度、max tokens 是调用参数，和优先级无关；测试会真实发一次要求 JSON 的请求。
          </p>
        </div>
        <button
          type="button"
          className={PRIMARY_BUTTON_CLASS}
          disabled={busy || editing !== null || providers.length === 0}
          onClick={() => setEditing("new")}
        >
          新增模型
        </button>
      </div>

      {error !== null && (
        <p className="mt-3 border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-700">{error}</p>
      )}

      {providers.length === 0 && (
        <p className="mt-3 text-[14px] leading-6 text-slate-500">先建一个供应商，模型必须有归属。</p>
      )}

      {models.length === 0 && providers.length > 0 && editing !== "new" && (
        <p className="mt-3 text-[14px] leading-6 text-slate-500">
          还没有模型。可以在供应商里"拉取模型"批量导入，也可以手工新增。
        </p>
      )}

      {models.length > 0 && (
        <table className="mt-3 w-full border-collapse text-[14px]">
          <thead>
            <tr className="border-b border-slate-200 text-left text-[13px] text-slate-400">
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">模型</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">供应商</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">参数</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">状态</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">最近测试</th>
              <th className="border-b border-slate-200 py-2 text-right font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => {
              const result = results[model.id];
              return (
                <Fragment key={model.id}>
                  <tr className="border-t border-slate-100 align-top">
                    <td className="py-2 pr-3">
                      <div className="font-medium text-slate-800">{model.display_name}</div>
                      <div className="text-[13px] text-slate-500">{model.model_id}</div>
                    </td>
                    <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                      {model.provider_name ?? "—"}
                    </td>
                    <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                      超时 {model.timeout_seconds}s · 温度{" "}
                      {model.temperature === null ? "默认" : model.temperature} · max{" "}
                      {model.max_tokens === null ? "默认" : model.max_tokens}
                    </td>
                    <td className="border-b border-slate-100 py-2 pr-3 text-[13px]">
                      <span
                        className={
                          "inline-flex items-center gap-1.5 " +
                          (model.enabled ? "text-emerald-700" : "text-slate-500")
                        }
                      >
                        <span
                          aria-hidden
                          className={
                            "h-1.5 w-1.5 shrink-0 rounded-full " +
                            (model.enabled ? "bg-emerald-500" : "bg-slate-400")
                          }
                        />
                        {model.enabled ? "启用" : "停用"}
                      </span>
                    </td>
                    <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                      {testLabel(model.last_test_status)}
                      {result !== undefined && (
                        <span className="ml-1 text-slate-400">{result.latency_ms}ms</span>
                      )}
                      <div className="text-slate-400">{formatTime(model.last_test_at)}</div>
                    </td>
                    <td className="border-b border-slate-100 py-2 text-right whitespace-nowrap">
                      <button
                        type="button"
                        className={BUTTON_CLASS + " mr-1"}
                        disabled={busy}
                        onClick={() => test(model)}
                      >
                        测试
                      </button>
                      <button
                        type="button"
                        className={BUTTON_CLASS + " mr-1"}
                        disabled={busy || editing !== null}
                        onClick={() => setEditing(model.id)}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className={DANGER_BUTTON_CLASS}
                        disabled={busy}
                        onClick={() => remove(model)}
                      >
                        删除
                      </button>
                    </td>
                  </tr>

                  {model.last_test_error !== null && (
                    <tr>
                      <td colSpan={6} className="pb-2 text-[13px] text-rose-600">
                        {model.last_test_error}
                      </td>
                    </tr>
                  )}

                  {editing === model.id && (
                    <tr>
                      <td colSpan={6} className="pb-3">
                        <ModelForm
                          providers={providers}
                          model={model}
                          busy={busy}
                          onSubmit={(input) => save(model, input)}
                          onCancel={() => setEditing(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}

      {newForm}
    </section>
  );
}

interface FormProps {
  providers: LlmProvider[];
  model: LlmModel | null;
  busy: boolean;
  onSubmit: (input: ModelInput | ModelPatchInput) => void;
  onCancel: () => void;
}

function ModelForm({ providers, model, busy, onSubmit, onCancel }: FormProps) {
  const enabledProviders = providers.filter((provider) => provider.enabled);
  const [providerId, setProviderId] = useState(
    model?.provider_id ?? enabledProviders[0]?.id ?? providers[0]?.id ?? 0,
  );
  const [modelId, setModelId] = useState(model?.model_id ?? "");
  const [displayName, setDisplayName] = useState(model?.display_name ?? "");
  const [timeout, setTimeoutSeconds] = useState(
    model === null ? "" : String(model.timeout_seconds),
  );
  const [temperature, setTemperature] = useState(
    model?.temperature === null || model?.temperature === undefined ? "" : String(model.temperature),
  );
  const [maxTokens, setMaxTokens] = useState(
    model?.max_tokens === null || model?.max_tokens === undefined ? "" : String(model.max_tokens),
  );
  const [enabled, setEnabled] = useState(model?.enabled ?? true);

  const submit = () => {
    const params = {
      display_name: displayName.trim() === "" ? undefined : displayName.trim(),
      timeout_seconds: optionalNumber(timeout),
      temperature: optionalNumber(temperature),
      max_tokens: optionalNumber(maxTokens),
      enabled,
    };
    if (model === null) {
      onSubmit({ ...params, provider_id: providerId, model_id: modelId.trim() });
      return;
    }
    onSubmit(params);
  };

  return (
    <div className="flex flex-col gap-3 border border-slate-200 bg-slate-50 px-5 py-4">
      {model === null ? (
        <>
          <label className={FORM_ROW_CLASS}>
            <span className={FORM_LABEL_CLASS}>供应商</span>
            <select
              className={SELECT_CLASS}
              value={providerId}
              onChange={(event) => setProviderId(Number(event.target.value))}
            >
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                  {provider.enabled ? "" : "（停用）"}
                </option>
              ))}
            </select>
          </label>
          <label className={FORM_ROW_CLASS}>
            <span className={FORM_LABEL_CLASS}>模型 ID</span>
            <input
              className={INPUT_CLASS}
              value={modelId}
              onChange={(event) => setModelId(event.target.value)}
              placeholder="网关里的 model 名称"
            />
          </label>
        </>
      ) : (
        <div className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>供应商</span>
          <span className="text-[13px] leading-5 text-slate-500">
            {model.provider_name ?? "—"}（模型 ID {model.model_id} 不可改）
          </span>
        </div>
      )}
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>显示名称</span>
        <input
          className={INPUT_CLASS}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder="留空则用模型 ID"
        />
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>超时（秒）</span>
        <input
          type="number"
          min={1}
          max={600}
          className={INPUT_CLASS + " w-24"}
          value={timeout}
          onChange={(event) => setTimeoutSeconds(event.target.value)}
          placeholder="90"
        />
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>温度</span>
        <input
          type="number"
          min={0}
          max={2}
          step={0.1}
          className={INPUT_CLASS + " w-20"}
          value={temperature}
          onChange={(event) => setTemperature(event.target.value)}
          placeholder="默认"
        />
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>max tokens</span>
        <input
          type="number"
          min={1}
          className={INPUT_CLASS + " w-24"}
          value={maxTokens}
          onChange={(event) => setMaxTokens(event.target.value)}
          placeholder="默认"
        />
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>启用</span>
        <input
          type="checkbox"
          className="justify-self-start"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
      </label>
      <div className={FORM_ROW_CLASS}>
        <span />
        <div className="flex gap-2">
          <button
            type="button"
            className={PRIMARY_BUTTON_CLASS}
            disabled={
              busy ||
              providerId === 0 ||
              (model === null && modelId.trim() === "")
            }
            onClick={submit}
          >
            保存
          </button>
          <button type="button" className={BUTTON_CLASS} disabled={busy} onClick={onCancel}>
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
