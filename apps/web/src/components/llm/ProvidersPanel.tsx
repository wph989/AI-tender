"use client";

/**
 * 供应商面板：连接信息、连通性测试与远端模型导入（设计文档 12 第 7、8 节）。
 *
 * 密钥只写不回显：编辑时输入框永远从空开始，"留空"表示不动，清除必须显式勾选
 * （后端用空串表达清除、用不传表达保持原值，见 api/llm.py 的 _store_key）。
 */

import { Fragment, useState } from "react";
import {
  ModelConfigurationFields,
  defaultConfiguration,
  type ModelConfiguration,
} from "./ModelConfigurationFields";

import {
  createProvider,
  deleteProvider,
  importModels,
  listRemoteModels,
  testProvider,
  updateProvider,
} from "@/lib/api/llm";
import {
  formatTime,
  message,
  validityLabel,
  kindLabel,
} from "@/lib/llm/format";
import type {
  AdapterProfile,
  LlmProvider,
  LlmTestResult,
  ProviderInput,
  ProviderPatchInput,
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
  profiles: AdapterProfile[];
  secretReady: boolean;
  onChanged: () => Promise<void>;
}

export function ProvidersPanel({
  providers,
  profiles,
  secretReady,
  onChanged,
}: Props) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [results, setResults] = useState<Record<number, LlmTestResult>>({});
  const [importingId, setImportingId] = useState<number | null>(null);
  const [remote, setRemote] = useState<string[] | null>(null);
  const [importMode, setImportMode] = useState("");
  const [importConfiguration, setImportConfiguration] =
    useState<ModelConfiguration | null>(null);
  const importProfile = profiles.find(
    (p) =>
      p.protocol ===
        providers.find((provider) => provider.id === importingId)?.protocol &&
      (!importMode || p.api_mode === importMode),
  );
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const run = async (fallback: string, task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await task();
    } catch (caught) {
      setError(message(caught, fallback));
    } finally {
      setBusy(false);
    }
  };

  const save = (
    provider: LlmProvider | null,
    input: ProviderInput | ProviderPatchInput,
  ) =>
    void run(
      provider === null ? "新建供应商失败" : "保存供应商失败",
      async () => {
        if (provider === null) await createProvider(input as ProviderInput);
        else await updateProvider(provider.id, input);
        setEditing(null);
        await onChanged();
      },
    );

  const remove = (provider: LlmProvider) => {
    if (
      !window.confirm(
        "删除供应商「" + provider.name + "」？其模型仍被功能绑定时会被拒绝。",
      )
    ) {
      return;
    }
    void run("删除供应商失败", async () => {
      await deleteProvider(provider.id);
      await onChanged();
    });
  };

  const test = (provider: LlmProvider) =>
    void run("测试供应商失败", async () => {
      const result = await testProvider(provider.id);
      setResults((previous) => ({ ...previous, [provider.id]: result }));
      await onChanged();
    });

  const openRemote = (provider: LlmProvider) =>
    void run("拉取远端模型失败", async () => {
      setImportingId(provider.id);
      setImportMode("");
      setImportConfiguration(null);
      setRemote(null);
      setChecked({});
      try {
        setRemote(await listRemoteModels(provider.id));
      } catch (e) {
        setImportingId(null);
        throw e;
      }
    });

  const closeRemote = () => {
    setImportingId(null);
    setRemote(null);
    setChecked({});
  };

  const selectedIds = Object.keys(checked).filter(
    (key) => checked[key] === true,
  );

  const importSelected = () =>
    void run("导入模型失败", async () => {
      if (importingId === null) return;
      const protocol = providers.find((p) => p.id === importingId)?.protocol;
      const compatible = profiles.filter((p) => p.protocol === protocol);
      const profile =
        compatible.find((p) => p.api_mode === importMode) ?? compatible[0];
      if (!profile) throw new Error("该协议暂无可导入的模型能力");
      const configuration =
        importConfiguration ?? defaultConfiguration(profile);
      const created = await importModels(importingId, selectedIds, profile, {
        capabilities: configuration.capabilities,
        supported_parameters: configuration.supported,
        parameters: Object.fromEntries(
          Object.entries(configuration.values).filter(
            ([key]) => !["temperature", "max_tokens"].includes(key),
          ),
        ),
        temperature:
          configuration.values.temperature == null
            ? null
            : Number(configuration.values.temperature),
        max_tokens:
          configuration.values.max_tokens == null
            ? null
            : Number(configuration.values.max_tokens),
      });
      setNotice(
        `已导入 ${created} 个模型，跳过 ${selectedIds.length - created} 个已有模型。新模型默认停用。`,
      );
      closeRemote();
      await onChanged();
    });

  return (
    <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">
            供应商
          </h2>
          <p className="mt-1 text-[13px] leading-5 text-slate-500">
            目录测试仅验证连接与目录协议；模型能力需要在模型页单独测试。
          </p>
        </div>
        <button
          type="button"
          className={PRIMARY_BUTTON_CLASS}
          disabled={busy || editing !== null}
          onClick={() => setEditing("new")}
        >
          新增供应商
        </button>
      </div>

      {!secretReady && (
        <p className="mt-3 text-sm text-amber-700">
          部署尚未配置有效的
          LLM_SECRET_KEYS，当前可保存元数据与匿名服务，暂不能新增或替换密钥。
        </p>
      )}
      {notice && (
        <p role="status" className="mt-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}
      {error !== null && (
        <p className="mt-3 border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-700">
          {error}
        </p>
      )}

      {providers.length === 0 && editing !== "new" && (
        <p className="mt-3 text-[14px] leading-6 text-slate-500">
          添加供应商并在功能页绑定模型后才能调用。模型与密钥均来自此处配置。
        </p>
      )}

      {providers.length > 0 && (
        <div
          className="settings-table-scroll"
          role="region"
          aria-label="配置列表"
          tabIndex={0}
        >
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[13px] text-slate-400">
                <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                  名称
                </th>
                <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                  Base URL
                </th>
                <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                  密钥
                </th>
                <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                  状态
                </th>
                <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                  最近测试
                </th>
                <th className="border-b border-slate-200 py-2 text-right font-normal">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {providers.map((provider) => {
                const result = results[provider.id];
                return (
                  <Fragment key={provider.id}>
                    <tr className="border-t border-slate-100 align-top">
                      <td className="py-2 pr-3 font-medium text-slate-800">
                        {provider.name}
                        <div className="text-xs text-slate-500">
                          {provider.protocol}
                        </div>
                      </td>
                      <td className="max-w-xs break-all py-2 pr-3 text-[13px] text-slate-600">
                        {provider.base_url}
                      </td>
                      <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                        {provider.auth_mode === "none"
                          ? "匿名"
                          : provider.has_api_key
                            ? (provider.api_key_hint ?? "已配置")
                            : "未配置"}
                      </td>
                      <td className="border-b border-slate-100 py-2 pr-3 text-[13px]">
                        <span
                          className={
                            "inline-flex items-center gap-1.5 " +
                            (provider.enabled
                              ? "text-emerald-700"
                              : "text-slate-500")
                          }
                        >
                          <span
                            aria-hidden
                            className={
                              "h-1.5 w-1.5 shrink-0 rounded-full " +
                              (provider.enabled
                                ? "bg-emerald-500"
                                : "bg-slate-400")
                            }
                          />
                          {provider.enabled ? "启用" : "停用"}
                        </span>
                      </td>
                      <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                        {validityLabel(provider.test_validity)}
                        {result !== undefined && (
                          <span className="ml-1 text-slate-400">
                            {result.latency_ms}ms
                          </span>
                        )}
                        <div className="text-slate-400">
                          {formatTime(provider.last_test_at)}
                        </div>
                      </td>
                      <td className="border-b border-slate-100 py-2 text-right whitespace-nowrap">
                        <button
                          type="button"
                          className={BUTTON_CLASS + " mr-1"}
                          disabled={busy}
                          onClick={() => test(provider)}
                        >
                          测试
                        </button>
                        <button
                          type="button"
                          className={BUTTON_CLASS + " mr-1"}
                          disabled={busy}
                          onClick={() => openRemote(provider)}
                        >
                          拉取模型
                        </button>
                        <button
                          type="button"
                          className={BUTTON_CLASS + " mr-1"}
                          disabled={busy || editing !== null}
                          onClick={() => setEditing(provider.id)}
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          className={DANGER_BUTTON_CLASS}
                          disabled={busy}
                          onClick={() => remove(provider)}
                        >
                          删除
                        </button>
                      </td>
                    </tr>

                    {provider.last_test_error !== null && (
                      <tr>
                        <td
                          colSpan={6}
                          className="pb-2 text-[13px] text-rose-600"
                        >
                          {provider.last_test_error}
                        </td>
                      </tr>
                    )}

                    {editing === provider.id && (
                      <tr>
                        <td colSpan={6} className="pb-3">
                          <ProviderForm
                            provider={provider}
                            profiles={profiles}
                            secretReady={secretReady}
                            busy={busy}
                            onSubmit={(input) => save(provider, input)}
                            onCancel={() => setEditing(null)}
                          />
                        </td>
                      </tr>
                    )}

                    {importingId === provider.id && (
                      <tr>
                        <td colSpan={6} className="pb-3">
                          <div className="border border-slate-200 bg-slate-50 px-4 py-3.5">
                            {remote === null ? (
                              <p className="text-[13px] text-slate-500">
                                正在拉取远端模型…
                              </p>
                            ) : remote.length === 0 ? (
                              <p className="text-[13px] text-slate-500">
                                远端没有返回模型（部分兼容网关不实现
                                /v1/models）。
                              </p>
                            ) : (
                              <>
                                <p className="text-[13px] text-slate-500">
                                  勾选并确认能力。已有模型跳过；新模型默认停用，确认参数后再启用。目录不证明模型能力。
                                </p>
                                <select
                                  aria-label="导入模型能力"
                                  className={SELECT_CLASS}
                                  value={
                                    importMode ||
                                    profiles.find(
                                      (p) => p.protocol === provider.protocol,
                                    )?.api_mode ||
                                    ""
                                  }
                                  onChange={(e) => {
                                    setImportMode(e.target.value);
                                    setImportConfiguration(
                                      defaultConfiguration(
                                        profiles.find(
                                          (profile) =>
                                            profile.protocol ===
                                              provider.protocol &&
                                            profile.api_mode === e.target.value,
                                        ),
                                      ),
                                    );
                                  }}
                                >
                                  {profiles
                                    .filter(
                                      (p) => p.protocol === provider.protocol,
                                    )
                                    .map((p) => (
                                      <option
                                        key={p.api_mode}
                                        value={p.api_mode}
                                      >
                                        {kindLabel[p.kind]} · {p.api_mode}
                                      </option>
                                    ))}
                                </select>
                                {importProfile && (
                                  <div className="my-4">
                                    <ModelConfigurationFields
                                      profile={importProfile}
                                      value={
                                        importConfiguration ??
                                        defaultConfiguration(importProfile)
                                      }
                                      onChange={setImportConfiguration}
                                    />
                                  </div>
                                )}
                                <div className="mt-2 grid max-h-56 grid-cols-2 gap-1 overflow-auto">
                                  {remote.map((modelId) => (
                                    <label
                                      key={modelId}
                                      className="flex items-center gap-2 text-[13px] text-slate-700"
                                    >
                                      <input
                                        type="checkbox"
                                        checked={checked[modelId] === true}
                                        onChange={(event) =>
                                          setChecked((previous) => ({
                                            ...previous,
                                            [modelId]: event.target.checked,
                                          }))
                                        }
                                      />
                                      {modelId}
                                    </label>
                                  ))}
                                </div>
                                <div className="mt-2 flex gap-2">
                                  <button
                                    type="button"
                                    className={PRIMARY_BUTTON_CLASS}
                                    disabled={
                                      busy ||
                                      selectedIds.length === 0 ||
                                      selectedIds.length > 100
                                    }
                                    onClick={importSelected}
                                  >
                                    导入选中的 {selectedIds.length} 个
                                  </button>
                                  <button
                                    type="button"
                                    className={BUTTON_CLASS}
                                    onClick={closeRemote}
                                  >
                                    取消
                                  </button>
                                </div>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {editing === "new" && (
        <div className="mt-3">
          <ProviderForm
            provider={null}
            profiles={profiles}
            secretReady={secretReady}
            busy={busy}
            onSubmit={(input) => save(null, input)}
            onCancel={() => setEditing(null)}
          />
        </div>
      )}
    </section>
  );
}

interface FormProps {
  profiles: AdapterProfile[];
  secretReady: boolean;
  provider: LlmProvider | null;
  busy: boolean;
  onSubmit: (input: ProviderInput | ProviderPatchInput) => void;
  onCancel: () => void;
}

function ProviderForm({
  provider,
  profiles,
  secretReady,
  busy,
  onSubmit,
  onCancel,
}: FormProps) {
  const [revision] = useState(provider?.revision);
  const [protocol, setProtocol] = useState(
    provider?.protocol ?? "openai_compatible",
  );
  const [authMode, setAuthMode] = useState<"api_key" | "none">(
    provider?.auth_mode ?? "api_key",
  );
  const [name, setName] = useState(provider?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(provider?.enabled ?? true);
  const [clearKey, setClearKey] = useState(false);

  const submit = () => {
    const common = {
      name: name.trim(),
      base_url: baseUrl.trim(),
      enabled,
      auth_mode: authMode,
    };
    if (provider === null) {
      onSubmit(
        apiKey === ""
          ? { ...common, protocol }
          : { ...common, protocol, api_key: apiKey },
      );
      return;
    }
    const patch: ProviderPatchInput = { ...common, revision };
    if (clearKey) patch.clear_api_key = true;
    else if (apiKey !== "") patch.api_key = apiKey;
    onSubmit(patch);
  };

  return (
    <fieldset
      disabled={busy}
      className="min-w-0 flex flex-col gap-3 border border-slate-200 bg-slate-50 px-5 py-4"
    >
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>名称</span>
        <input
          className={INPUT_CLASS}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="如 内网网关"
        />
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>协议</span>
        <select
          className={SELECT_CLASS}
          value={protocol}
          disabled={provider !== null}
          onChange={(e) => setProtocol(e.target.value)}
        >
          {Array.from(new Set(profiles.map((p) => p.protocol))).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>认证</span>
        <select
          className={SELECT_CLASS}
          value={authMode}
          onChange={(e) => setAuthMode(e.target.value as "api_key" | "none")}
        >
          <option value="api_key">API Key</option>
          <option value="none">匿名服务（无需密钥）</option>
        </select>
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>Base URL</span>
        <input
          className={INPUT_CLASS}
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          placeholder="https://gateway.example/v1"
        />
      </label>
      <label className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>API Key</span>
        <input
          type="password"
          autoComplete="new-password"
          disabled={!secretReady || clearKey || authMode === "none"}
          className={INPUT_CLASS}
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={
            provider === null
              ? "稍后填写也可保存，调用前需配置"
              : "留空保持不变"
          }
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
      {provider !== null && (
        <label className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>清除已存密钥</span>
          <input
            type="checkbox"
            className="justify-self-start"
            checked={clearKey}
            onChange={(event) => setClearKey(event.target.checked)}
          />
        </label>
      )}
      <div className={FORM_ROW_CLASS}>
        <span />
        <div className="flex gap-2">
          <button
            type="button"
            className={PRIMARY_BUTTON_CLASS}
            disabled={busy || name.trim() === "" || baseUrl.trim() === ""}
            onClick={submit}
          >
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
      </div>
      {provider !== null && (
        <div className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>当前密钥</span>
          <span className="text-[13px] leading-5 text-slate-500">
            {provider.auth_mode === "none"
              ? "匿名"
              : provider.has_api_key
                ? (provider.api_key_hint ?? "已配置")
                : "未配置"}
            ；保存后写入加密密文，页面不再回显。
          </span>
        </div>
      )}
    </fieldset>
  );
}
