"use client";

import { useEffect, useState } from "react";
import {
  ModelConfigurationFields,
  defaultConfiguration,
  type ModelConfiguration,
} from "./ModelConfigurationFields";
import {
  createModel,
  deleteModel,
  startModelTest,
  updateModel,
} from "@/lib/api/llm";
import {
  formatTime,
  kindLabel,
  capabilityLabel,
  message,
  validityLabel,
} from "@/lib/llm/format";
import type {
  AdapterProfile,
  LlmModel,
  LlmProvider,
  ModelInput,
  ModelPatchInput,
  ModelKind,
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
  profiles: AdapterProfile[];
  onChanged: () => Promise<void>;
}

export function ModelsPanel({ providers, models, profiles, onChanged }: Props) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTests, setSelectedTests] = useState<Record<number, string>>(
    {},
  );
  const [embeddingType, setEmbeddingType] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [kind, setKind] = useState("");
  const [provider, setProvider] = useState("");
  const [state, setState] = useState("");
  const run = async (task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await task();
      await onChanged();
    } catch (e) {
      setError(message(e, "操作失败"));
    } finally {
      setBusy(false);
    }
  };
  const save = (input: ModelInput | ModelPatchInput) =>
    void run(async () => {
      if (editing === "new") await createModel(input as ModelInput);
      else if (editing !== null) await updateModel(editing, input);
      setEditing(null);
    });
  const hasRunningTests = models.some((model) =>
    Object.values(model.capability_tests).some(
      (test) => test.status === "running",
    ),
  );
  useEffect(() => {
    if (!hasRunningTests) return;
    // 刷新页面后继续读取持久测试，不重新发送请求；切走或测试结束时停止轮询。
    const timer = window.setInterval(() => {
      void onChanged().catch((e) => setError(message(e, "读取测试状态失败")));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [hasRunningTests, onChanged]);
  const test = async (model: LlmModel) => {
    await run(async () => {
      const capability =
        selectedTests[model.id] ??
        (model.embedding_input_type === "multimodal"
          ? "multimodal_embedding"
          : model.test_capabilities[0]);
      if (!capability) throw new Error("该模型没有可测试能力");
      const result = await startModelTest(model.id, capability);
      setNotice(
        `${model.display_name} 的${capabilityLabel[capability]}测试已受理（#${result.test_id}），结果将自动更新。`,
      );
    });
  };
  const visible = models.filter(
    (m) =>
      (!kind || m.kind === kind) &&
      (!embeddingType || m.embedding_input_type === embeddingType) &&
      (!provider || String(m.provider_id) === provider) &&
      (!state ||
        (state === "enabled"
          ? m.enabled && m.provider_enabled
          : !m.enabled || !m.provider_enabled)),
  );
  return (
    <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-[19px] font-semibold">模型</h2>
          <p className="mt-1 text-sm text-slate-500">
            按能力配置并测试。测试会发送一次真实请求，可能产生费用，不会自动重试或切换模型。
          </p>
        </div>
        <button
          className={PRIMARY_BUTTON_CLASS}
          disabled={busy || editing !== null || !providers.length}
          onClick={() => setEditing("new")}
        >
          新增模型
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        四类模型按接口声明能力；视觉和图文嵌入单独测试。测试图片只供临时预览。
      </p>
      {hasRunningTests && (
        <p role="status" className="mt-3 text-sm text-slate-500">
          测试进行中，刷新页面可继续查看。本地模型首次加载可能较慢。
        </p>
      )}
      {notice && (
        <p role="status" className="mt-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <select
          aria-label="按模型种类筛选"
          className={SELECT_CLASS}
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">全部种类</option>
          {Object.entries(kindLabel).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select
          aria-label="按嵌入输入类型筛选"
          className={SELECT_CLASS}
          value={embeddingType}
          onChange={(e) => setEmbeddingType(e.target.value)}
        >
          <option value="">全部输入类型</option>
          <option value="text">纯文本嵌入</option>
          <option value="multimodal">文本＋图片嵌入</option>
        </select>
        <select
          aria-label="按供应商筛选"
          className={SELECT_CLASS}
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="">全部供应商</option>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <select
          aria-label="按模型状态筛选"
          className={SELECT_CLASS}
          value={state}
          onChange={(e) => setState(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="enabled">已启用</option>
          <option value="disabled">模型或供应商停用</option>
        </select>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-rose-700">
          {error}
        </p>
      )}
      {editing !== null && (
        <ModelForm
          key={editing}
          providers={providers}
          model={models.find((m) => m.id === editing) ?? null}
          profiles={profiles}
          busy={busy}
          onSubmit={save}
          onCancel={() => setEditing(null)}
        />
      )}
      <div className="mt-4 space-y-3">
        {visible.map((m) => (
          <article
            key={m.id}
            className="rounded-xl border border-slate-200 p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="break-all font-semibold">{m.display_name}</h3>
                <p className="break-all text-xs text-slate-500">
                  {m.provider_name} · {m.model_id}
                </p>
              </div>
              <span className="rounded-full bg-violet-50 px-3 py-1 text-xs text-violet-700">
                {kindLabel[m.kind]}
                {m.embedding_input_type === "multimodal"
                  ? " · 文本＋图片"
                  : m.embedding_input_type === "text"
                    ? " · 纯文本"
                    : m.capabilities.includes("image_input")
                      ? " · 视觉"
                      : ""}
              </span>
            </div>
            <p className="mt-3 text-sm text-slate-600">
              {m.api_mode} · 超时 {m.timeout_seconds}s · 失败后额外重试{" "}
              {m.extra_retries} 次
            </p>
            {m.kind === "language" && (
              <p className="mt-1 text-xs text-slate-500">
                温度 {m.temperature ?? "服务默认"} · 输出上限{" "}
                {m.max_tokens ?? "服务默认"}
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-slate-500">
                <span
                  className={
                    m.enabled && m.provider_enabled ? "text-emerald-700" : ""
                  }
                >
                  {!m.provider_enabled
                    ? "供应商停用"
                    : m.enabled
                      ? "已启用"
                      : "已停用"}
                </span>{" "}
                ·{" "}
                {m.capabilities.map((c) => capabilityLabel[c] ?? c).join(" / ")}
                <p className="mt-1">{formatTime(m.last_test_at)}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <select
                  aria-label={`${m.display_name} 测试能力`}
                  className={SELECT_CLASS}
                  value={
                    selectedTests[m.id] ??
                    (m.embedding_input_type === "multimodal"
                      ? "multimodal_embedding"
                      : m.test_capabilities[0])
                  }
                  onChange={(e) =>
                    setSelectedTests((old) => ({
                      ...old,
                      [m.id]: e.target.value,
                    }))
                  }
                  disabled={busy}
                >
                  {m.test_capabilities.map((cap) => (
                    <option key={cap} value={cap}>
                      {capabilityLabel[cap]}
                    </option>
                  ))}
                </select>
                <button
                  className={BUTTON_CLASS}
                  disabled={
                    busy ||
                    Object.values(m.capability_tests).some(
                      (t) => t.status === "running",
                    )
                  }
                  onClick={() => void test(m)}
                >
                  {Object.values(m.capability_tests).some(
                    (t) => t.status === "running",
                  )
                    ? "测试中…"
                    : "测试"}
                </button>
                <button
                  className={BUTTON_CLASS}
                  disabled={busy || editing !== null}
                  onClick={() => setEditing(m.id)}
                >
                  编辑
                </button>
                <button
                  className={DANGER_BUTTON_CLASS}
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `删除模型「${m.display_name}」？有效绑定或索引引用会阻止删除。`,
                      )
                    )
                      void run(() => deleteModel(m.id));
                  }}
                >
                  删除
                </button>
              </div>
            </div>
            <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
              {m.test_capabilities.map((cap) => {
                const check = m.capability_tests[cap];
                return (
                  <div key={cap} className="text-xs text-slate-600">
                    <span className="font-medium">{capabilityLabel[cap]}</span>{" "}
                    · {validityLabel(check?.validity ?? "untested")}
                    {check?.latency_ms != null &&
                      ` · ${(check.latency_ms / 1000).toFixed(1)} 秒`}
                    {check?.result.vector_count != null &&
                      ` · ${check.result.vector_count} 条 ${check.result.embedding_dimensions} 维向量`}
                    {check?.error_message && (
                      <p className="mt-1 text-rose-700">
                        {check.error_message}
                      </p>
                    )}
                    {check?.validity === "valid" &&
                      check.result.preview_url && (
                        <figure className="mt-2">
                          {/* 预览来自本项目后端，禁止浏览器直接访问供应商图片地址。 */}
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={check.result.preview_url}
                            alt="本次生图测试预览"
                            className="max-h-64 max-w-full rounded-lg border border-slate-200"
                          />
                          <figcaption className="mt-1">
                            临时测试图片，有效至 {formatTime(check.expires_at)}
                            。
                          </figcaption>
                        </figure>
                      )}
                  </div>
                );
              })}
            </div>
            {m.last_test_error &&
              Object.keys(m.capability_tests).length === 0 && (
                <p className="mt-2 text-sm text-rose-700">
                  {m.last_test_error}
                </p>
              )}
          </article>
        ))}
      </div>
      {!visible.length && (
        <p className="mt-6 text-sm text-slate-500">
          暂无符合条件的模型，可手动添加或从供应商目录导入。
        </p>
      )}
    </section>
  );
}

function ModelForm({
  providers,
  model,
  profiles,
  busy,
  onSubmit,
  onCancel,
}: {
  providers: LlmProvider[];
  model: LlmModel | null;
  profiles: AdapterProfile[];
  busy: boolean;
  onSubmit: (input: ModelInput | ModelPatchInput) => void;
  onCancel: () => void;
}) {
  const [revision] = useState(model?.revision);
  const [providerId, setProviderId] = useState(
    model?.provider_id ?? providers[0]?.id ?? 0,
  );
  const [modelId, setModelId] = useState(model?.model_id ?? "");
  const [name, setName] = useState(model?.display_name ?? "");
  const initialProvider = providers.find((p) => p.id === providerId);
  const initialProfile = profiles.find(
    (p) =>
      p.protocol === initialProvider?.protocol &&
      (!model || (p.kind === model.kind && p.api_mode === model.api_mode)),
  );
  const [modelKind, setModelKind] = useState<ModelKind>(
    model?.kind ?? initialProfile?.kind ?? "language",
  );
  const [mode, setMode] = useState(
    model?.api_mode ?? initialProfile?.api_mode ?? "",
  );
  const [configuration, setConfiguration] = useState<ModelConfiguration>(() =>
    model
      ? {
          capabilities: model.capabilities,
          supported: model.supported_parameters,
          values: {
            ...model.parameters,
            ...(model.temperature != null
              ? { temperature: model.temperature }
              : {}),
            ...(model.max_tokens != null
              ? { max_tokens: model.max_tokens }
              : {}),
          },
        }
      : defaultConfiguration(initialProfile),
  );
  const [timeout, setTimeoutValue] = useState(
    String(model?.timeout_seconds ?? 90),
  );
  const [retries, setRetries] = useState(String(model?.extra_retries ?? 1));
  const [enabled, setEnabled] = useState(model?.enabled ?? false);
  const provider = providers.find((p) => p.id === providerId);
  const available = profiles.filter((p) => p.protocol === provider?.protocol);
  const selected = available.find(
    (p) => p.kind === modelKind && p.api_mode === mode,
  );
  const chooseProfile = (profile?: AdapterProfile) => {
    setMode(profile?.api_mode ?? "");
    setConfiguration(defaultConfiguration(profile));
  };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    // 空输入明确发送 null，保证编辑时可以清除旧参数。
    const params: ModelPatchInput = {
      display_name: name.trim() || modelId.trim(),
      kind: selected.kind,
      api_mode: selected.api_mode,
      capabilities: configuration.capabilities,
      supported_parameters: configuration.supported,
      parameters: Object.fromEntries(
        Object.entries(configuration.values).filter(
          ([key]) => !["temperature", "max_tokens"].includes(key),
        ),
      ),
      timeout_seconds: Number(timeout),
      extra_retries: Number(retries),
      enabled,
      temperature:
        configuration.values.temperature == null
          ? null
          : Number(configuration.values.temperature),
      max_tokens:
        configuration.values.max_tokens == null
          ? null
          : Number(configuration.values.max_tokens),
    };
    onSubmit(
      model
        ? { ...params, revision }
        : { ...params, provider_id: providerId, model_id: modelId.trim() },
    );
  };
  return (
    <form
      onSubmit={submit}
      className="mt-4 space-y-3 rounded-xl border border-violet-200 bg-violet-50/40 p-4"
    >
      <fieldset disabled={busy} className="min-w-0 space-y-3">
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>供应商</span>
          <select
            className={SELECT_CLASS}
            disabled={model !== null || busy}
            value={providerId}
            onChange={(e) => {
              setProviderId(Number(e.target.value));
              const next = profiles.find(
                (p) =>
                  p.protocol ===
                  providers.find(
                    (provider) => provider.id === Number(e.target.value),
                  )?.protocol,
              );
              setModelKind(next?.kind ?? "language");
              chooseProfile(next);
            }}
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.protocol}
              </option>
            ))}
          </select>
        </label>
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>模型 ID</span>
          <input
            className={INPUT_CLASS}
            required
            disabled={model !== null || busy}
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
          />
        </label>
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>名称</span>
          <input
            className={INPUT_CLASS}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="留空使用模型 ID"
          />
        </label>
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>模型种类</span>
          <select
            className={SELECT_CLASS}
            value={modelKind}
            onChange={(e) => {
              const kind = e.target.value as ModelKind;
              setModelKind(kind);
              chooseProfile(available.find((p) => p.kind === kind));
            }}
          >
            {Object.entries(kindLabel).map(([kind, label]) => (
              <option key={kind} value={kind}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>接口模式</span>
          <select
            className={SELECT_CLASS}
            value={selected?.api_mode ?? ""}
            onChange={(e) =>
              chooseProfile(
                available.find(
                  (p) => p.kind === modelKind && p.api_mode === e.target.value,
                ),
              )
            }
          >
            {!selected && <option value="">此协议尚不支持该类模型</option>}
            {available
              .filter((p) => p.kind === modelKind)
              .map((p) => (
                <option key={p.api_mode} value={p.api_mode}>
                  {p.api_mode}
                </option>
              ))}
          </select>
        </label>
        {selected && (
          <ModelConfigurationFields
            profile={selected}
            value={configuration}
            onChange={setConfiguration}
          />
        )}
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>超时（秒）</span>
          <input
            className={INPUT_CLASS}
            type="number"
            min={1}
            max={600}
            required
            value={timeout}
            onChange={(e) => setTimeoutValue(e.target.value)}
          />
        </label>
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>失败后额外重试</span>
          <div>
            <input
              aria-label="失败后额外重试次数"
              className={INPUT_CLASS}
              type="number"
              min={0}
              max={10}
              step={1}
              required
              value={retries}
              onChange={(e) => setRetries(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              1
              表示首次请求外再试一次；仅暂时故障重试。嵌入和重排目前每次只请求一次。
            </p>
          </div>
        </label>
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>启用</span>
          <input
            className="justify-self-start"
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
        </label>
        <div className="flex gap-2">
          <button className={PRIMARY_BUTTON_CLASS} disabled={busy || !selected}>
            保存
          </button>
          <button
            type="button"
            className={BUTTON_CLASS}
            disabled={busy}
            onClick={onCancel}
          >
            取消
          </button>
        </div>
      </fieldset>
    </form>
  );
}
