"use client";

/**
 * 供应商面板：连接信息、连通性测试与远端模型导入（设计文档 12 第 7、8 节）。
 *
 * 密钥只写不回显：编辑时输入框永远从空开始，"留空"表示不动，清除必须显式勾选
 * （后端用空串表达清除、用不传表达保持原值，见 api/llm.py 的 _store_key）。
 */

import { Fragment, useState } from "react";

import {
  createProvider,
  deleteProvider,
  importModels,
  listRemoteModels,
  testProvider,
  updateProvider,
} from "@/lib/api/llm";
import { formatTime, message, testLabel } from "@/lib/llm/format";
import type { LlmProvider, LlmTestResult, ProviderInput, ProviderPatchInput } from "@/types/llm";

import {
  BUTTON_CLASS,
  DANGER_BUTTON_CLASS,
  FORM_LABEL_CLASS,
  FORM_ROW_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
} from "./ui";

interface Props {
  providers: LlmProvider[];
  onChanged: () => Promise<void>;
}

export function ProvidersPanel({ providers, onChanged }: Props) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<number, LlmTestResult>>({});
  const [importingId, setImportingId] = useState<number | null>(null);
  const [remote, setRemote] = useState<string[] | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});

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

  const save = (provider: LlmProvider | null, input: ProviderInput | ProviderPatchInput) =>
    void run(provider === null ? "新建供应商失败" : "保存供应商失败", async () => {
      if (provider === null) await createProvider(input as ProviderInput);
      else await updateProvider(provider.id, input);
      setEditing(null);
      await onChanged();
    });

  const remove = (provider: LlmProvider) => {
    if (!window.confirm("删除供应商「" + provider.name + "」？其模型仍被功能绑定时会被拒绝。")) {
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
      setRemote(null);
      setChecked({});
      setRemote(await listRemoteModels(provider.id));
    });

  const closeRemote = () => {
    setImportingId(null);
    setRemote(null);
    setChecked({});
  };

  const selectedIds = Object.keys(checked).filter((key) => checked[key] === true);

  const importSelected = () =>
    void run("导入模型失败", async () => {
      if (importingId === null) return;
      await importModels(importingId, selectedIds);
      closeRemote();
      await onChanged();
    });

  return (
    <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">供应商</h2>
          <p className="mt-1 text-[13px] leading-5 text-slate-500">
            连接你的模型服务。添加服务地址与密钥后，可测试连接并获取可用模型。
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

      {error !== null && (
        <p className="mt-3 border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-700">{error}</p>
      )}

      {providers.length === 0 && editing !== "new" && (
        <p className="mt-3 text-[14px] leading-6 text-slate-500">
          添加一个供应商以管理模型连接。未添加时将使用部署时配置的默认模型。
        </p>
      )}

      {providers.length > 0 && (
        <div className="settings-table-scroll" role="region" aria-label="配置列表" tabIndex={0}><table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-slate-200 text-left text-[13px] text-slate-400">
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">名称</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">Base URL</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">密钥</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">状态</th>
              <th className="border-b border-slate-200 py-2 pr-3 font-normal">最近测试</th>
              <th className="border-b border-slate-200 py-2 text-right font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((provider) => {
              const result = results[provider.id];
              return (
                <Fragment key={provider.id}>
                  <tr className="border-t border-slate-100 align-top">
                    <td className="py-2 pr-3 font-medium text-slate-800">{provider.name}</td>
                    <td className="max-w-xs break-all py-2 pr-3 text-[13px] text-slate-600">
                      {provider.base_url}
                    </td>
                    <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                      {provider.has_api_key ? "****" + (provider.api_key_hint ?? "") : "未配置"}
                    </td>
                    <td className="border-b border-slate-100 py-2 pr-3 text-[13px]">
                      <span
                        className={
                          "inline-flex items-center gap-1.5 " +
                          (provider.enabled ? "text-emerald-700" : "text-slate-500")
                        }
                      >
                        <span
                          aria-hidden
                          className={
                            "h-1.5 w-1.5 shrink-0 rounded-full " +
                            (provider.enabled ? "bg-emerald-500" : "bg-slate-400")
                          }
                        />
                        {provider.enabled ? "启用" : "停用"}
                      </span>
                    </td>
                    <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                      {testLabel(provider.last_test_status)}
                      {result !== undefined && (
                        <span className="ml-1 text-slate-400">{result.latency_ms}ms</span>
                      )}
                      <div className="text-slate-400">{formatTime(provider.last_test_at)}</div>
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
                      <td colSpan={6} className="pb-2 text-[13px] text-rose-600">
                        {provider.last_test_error}
                      </td>
                    </tr>
                  )}

                  {editing === provider.id && (
                    <tr>
                      <td colSpan={6} className="pb-3">
                        <ProviderForm
                          provider={provider}
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
                            <p className="text-[13px] text-slate-500">正在拉取远端模型…</p>
                          ) : remote.length === 0 ? (
                            <p className="text-[13px] text-slate-500">
                              远端没有返回模型（部分兼容网关不实现 /v1/models）。
                            </p>
                          ) : (
                            <>
                              <p className="text-[13px] text-slate-500">
                                勾选要导入的模型；已存在的会被重新启用，不会重复建行。
                              </p>
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
                                  disabled={busy || selectedIds.length === 0}
                                  onClick={importSelected}
                                >
                                  导入选中的 {selectedIds.length} 个
                                </button>
                                <button type="button" className={BUTTON_CLASS} onClick={closeRemote}>
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
        </table></div>
      )}

      {editing === "new" && (
        <div className="mt-3">
          <ProviderForm
            provider={null}
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
  provider: LlmProvider | null;
  busy: boolean;
  onSubmit: (input: ProviderInput | ProviderPatchInput) => void;
  onCancel: () => void;
}

function ProviderForm({ provider, busy, onSubmit, onCancel }: FormProps) {
  const [name, setName] = useState(provider?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(provider?.enabled ?? true);
  const [clearKey, setClearKey] = useState(false);

  const submit = () => {
    const common = { name: name.trim(), base_url: baseUrl.trim(), enabled };
    if (provider === null) {
      onSubmit(apiKey === "" ? common : { ...common, api_key: apiKey });
      return;
    }
    const patch: ProviderPatchInput = { ...common };
    if (clearKey) patch.api_key = "";
    else if (apiKey !== "") patch.api_key = apiKey;
    onSubmit(patch);
  };

  return (
    <div className="flex flex-col gap-3 border border-slate-200 bg-slate-50 px-5 py-4">
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
          className={INPUT_CLASS}
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={provider === null ? "可留空，用 .env 的 LLM_API_KEY" : "留空保持不变"}
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
          <button type="button" className={BUTTON_CLASS} disabled={busy} onClick={onCancel}>
            取消
          </button>
        </div>
      </div>
      {provider !== null && (
        <div className={FORM_ROW_CLASS}>
          <span className={FORM_LABEL_CLASS}>当前密钥</span>
          <span className="text-[13px] leading-5 text-slate-500">
            {provider.has_api_key ? "****" + (provider.api_key_hint ?? "") : "未配置"}
            ；保存后写入加密密文，页面不再回显。
          </span>
        </div>
      )}
    </div>
  );
}
