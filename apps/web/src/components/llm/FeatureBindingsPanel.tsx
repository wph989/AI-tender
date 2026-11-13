"use client";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { useFeedback } from "@/hooks/useFeedback";
import { App, Button, ConfigProvider, Input, Select, Tabs } from "antd";

/**
 * 功能绑定面板：给功能选模型、排优先级、改不同候选上限（设计文档 12 第 3、4、8 节）。
 *
 * 优先级是"整表"的：草稿就是一份有序的模型行 id 数组，任何排序动作都只改这份数组，
 * 保存时整表 PUT（服务端按位置写 1..N）。单行改数字会造出空洞与同级，接口也不接受。
 */

import { useState } from "react";

import { replaceBindings } from "@/lib/api/llm";
import { message, withinNumericRule } from "@/lib/llm/format";
import { moveToPriority } from "@/lib/llm/priority";
import type { LlmFeature, LlmModel, ParameterSchema } from "@/types/llm";

interface Props {
  features: LlmFeature[];
  models: LlmModel[];
  fields?: Record<string, ParameterSchema>;
  maximumBindings?: number;
  onChanged: () => Promise<void>;
}

interface Draft {
  key: string;
  ids: number[];
  limit: number;
  total: number;
  revision: number;
}

export function FeatureBindingsPanel({ features, models, fields = {}, maximumBindings, onChanged }: Props) {
  const { message: toast } = App.useApp();
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [pendingAdd, setPendingAdd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useFeedback(error);
  useUnsavedChanges(Object.keys(drafts).length > 0, busy);

  const active =
    features.find((feature) => feature.key === activeKey) ?? features[0];
  const draft = active ? (drafts[active.key] ?? null) : null;
  if (active === undefined) {
    return (
      <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">
          功能绑定
        </h2>
        <p className="mt-3 text-[14px] leading-6 text-slate-500">
          后端没有返回功能列表。
        </p>
      </section>
    );
  }

  const serverIds = active.bindings.map((binding) => binding.model_row_id);
  // 每个功能保留独立草稿，切换功能和刷新服务端快照都不能清除未保存的排序。
  const setDraft = (value: Draft | null) =>
    setDrafts((previous) => {
      const next = { ...previous };
      if (value) next[active.key] = value;
      else delete next[active.key];
      return next;
    });
  const ids =
    draft !== null && draft.key === active.key ? draft.ids : serverIds;
  const limit =
    draft !== null && draft.key === active.key
      ? draft.limit
      : active.failover_limit;
  const total =
    draft?.key === active.key ? draft.total : active.max_total_requests;
  const revision = draft?.key === active.key ? draft.revision : active.revision;
  const dirty =
    total !== active.max_total_requests ||
    ids.join(",") !== serverIds.join(",") ||
    limit !== active.failover_limit;

  const update = (
    nextIds: number[],
    nextLimit: number = limit,
    nextTotal: number = total,
  ) =>
    setDraft({
      key: active.key,
      ids: nextIds,
      limit: nextLimit,
      total: nextTotal,
      revision,
    });

  const run = async (fallback: string, task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (caught) {
      setError(message(caught, fallback));
      // 刷新只更新服务端基线，草稿继续保留，用户可比较冲突的最新版本。
      await onChanged().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const save = () =>
    void run("保存绑定失败", async () => {
      // 排序和预算一次原子提交；旧版本失败时保留当前草稿供比较。
      await replaceBindings(active.key, ids, {
        revision,
        failover_limit: limit,
        max_total_requests: total,
      });
      setDraft(null);
      void toast.success("功能绑定已保存");
      await onChanged().catch(() => setError("绑定已保存，但刷新失败。"));
    });

  const modelById = new Map(models.map((model) => [model.id, model]));
  const unbound = models.filter(
    (model) =>
      active.binding_available !== false && !ids.includes(model.id) &&
      model.kind === active.required_kind &&
      (active.required_kind !== "language" ||
        model.capabilities.includes("json_output")),
  );
  const singleModel = ["embedding", "rerank"].includes(active.required_kind);
  const languageRouting = active.required_kind === "language";
  const maxBindings = singleModel ? 1 : (maximumBindings ?? models.length);
  const effective =
    Math.min(limit, ids.filter((id) => {
      const model = modelById.get(id);
      return model?.enabled && model.provider_enabled;
    }).length);

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
    if (ids.includes(modelRowId) || ids.length >= maxBindings) return;
    update([...ids, modelRowId]);
    setPendingAdd("");
  };

  return (
    <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
      <ConfigProvider componentDisabled={busy}>
        <fieldset disabled={busy} className="min-w-0">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">
                功能绑定
              </h2>
              <p className="mt-1 text-[13px] leading-5 text-slate-500">
                暂时故障按模型的额外次数重试，再尝试后续候选；请求总量与时间预算始终优先。
                图片生成目前仅支持在模型列表中测试，尚未接入业务功能绑定。
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2 whitespace-nowrap text-[13px] text-slate-600">
              不同候选上限
              <Input
                aria-label="不同候选上限"
                disabled={!languageRouting}
                type="number"
                min={fields.failover_limit?.min}
                max={fields.failover_limit?.max}
                className={" w-20"}
                value={limit}
                onChange={(event) => update(ids, Number(event.target.value))}
              />
              级
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <label>
              总请求上限{" "}
              <Input
                aria-label="总请求上限"
                disabled={!languageRouting}
                type="number"
                min={fields.max_total_requests?.min}
                max={fields.max_total_requests?.max}
                className={" w-20"}
                value={total}
                onChange={(e) => update(ids, limit, Number(e.target.value))}
              />
            </label>
          </div>
          {!languageRouting && (
            <p className="mt-2 text-xs text-slate-500">
              嵌入与重排当前为单次请求；上述转移与重试预算仅用于语言模型调用。
            </p>
          )}
          {draft && revision !== active.revision && (
            <p className="mt-3 text-sm text-amber-700">
              服务端配置已变化。当前草稿保留，请比较最新配置后放弃草稿并重新编辑。
            </p>
          )}
          <Tabs
            activeKey={active.key}
            onChange={(key) => {
              setActiveKey(key);
              setPendingAdd("");
              setError(null);
            }}
            items={features.map((feature) => ({
              key: feature.key,
              disabled: busy,
              label: `${feature.name} (${feature.bindings.length})`,
            }))}
          />
          <p className="mt-2 text-sm leading-6 text-slate-600">{active.description}</p>
          {error !== null && (
            <p className="mt-3 border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-700">
              {error}
            </p>
          )}

          <p className="mt-3 text-[13px] text-slate-500" hidden={!languageRouting}>
            共 {ids.length} 个候选，最多实际尝试 {effective} 个可用模型、{total}{" "}
            次请求。前面的模型可能耗尽预算，后续模型不保证执行。
          </p>

          {ids.length === 0 ? (
            <p className="mt-2 text-[14px] leading-6 text-slate-500">
              还未分配模型。语言功能暂停调用；向量或重排留空时使用基础检索。
            </p>
          ) : (
            <div
              className="settings-table-scroll"
              role="region"
              aria-label="功能模型列表"
              tabIndex={0}
            >
              <table className="w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-[13px] text-slate-400">
                    <th className="border-b border-slate-200 py-2 pr-3 font-normal w-16">
                      级别
                    </th>
                    <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                      模型
                    </th>
                    <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                      供应商
                    </th>
                    <th className="border-b border-slate-200 py-2 pr-3 font-normal">
                      状态
                    </th>
                    <th className="border-b border-slate-200 py-2 text-right font-normal">
                      调整
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ids.map((modelRowId, index) => {
                    const model = modelById.get(modelRowId);
                    return (
                      <tr
                        key={modelRowId}
                        className="border-t border-slate-100"
                      >
                        <td className="py-2 pr-3">
                          {/* 选择完整顺位后再移动，避免输入两位数字时第一位就触发重排。 */}
                          <Select<number>
                            className="w-28"
                            virtual={false}
                            aria-label={
                              (model?.display_name ?? "模型") + "优先级"
                            }
                            value={index + 1}
                            options={ids.map((_, position) => ({
                              value: position + 1,
                              label: position === 0 ? "1 · 首选" : `${position + 1} · 备选`,
                            }))}
                            onChange={(position) => setPriority(modelRowId, position)}
                          />
                        </td>
                        <td className="py-2 pr-3">
                          <div className="font-medium text-slate-800">
                            {model?.display_name ?? "模型 #" + modelRowId}
                          </div>
                          <div className="text-[13px] text-slate-500">
                            {model?.model_id ?? "已不在模型列表中"} · 理论最多{" "}
                            {!singleModel ? (model?.extra_retries ?? 0) + 1 : 1}{" "}
                            次
                          </div>
                        </td>
                        <td className="border-b border-slate-100 py-2 pr-3 text-[13px] text-slate-600">
                          {model?.provider_name ?? "—"}
                        </td>
                        <td className="border-b border-slate-100 py-2 pr-3 text-[13px]">
                          {model === undefined ? (
                            "—"
                          ) : model.enabled && model.provider_enabled ? (
                            <span className="inline-flex items-center gap-1.5 text-emerald-700">
                              <span
                                aria-hidden
                                className="h-1.5 w-1.5 rounded-full bg-emerald-500"
                              />
                              启用
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-slate-500">
                              <span
                                aria-hidden
                                className="h-1.5 w-1.5 rounded-full bg-slate-400"
                              />
                              停用
                            </span>
                          )}
                        </td>
                        <td className="border-b border-slate-100 py-2 text-right whitespace-nowrap">
                          <Button
                            htmlType="button"
                            className="mr-1"
                            disabled={index === 0}
                            aria-label={(model?.display_name ?? "模型") + "置顶"}
                            onClick={() => setPriority(modelRowId, 1)}
                          >
                            置顶
                          </Button>
                          <Button
                            htmlType="button"
                            className={" mr-1"}
                            disabled={index === 0}
                            aria-label={(model?.display_name ?? "模型") + "提高优先级"}
                            onClick={() => shift(index, -1)}
                          >
                            ↑
                          </Button>
                          <Button
                            htmlType="button"
                            className={" mr-1"}
                            disabled={index === ids.length - 1}
                            aria-label={(model?.display_name ?? "模型") + "降低优先级"}
                            onClick={() => shift(index, 1)}
                          >
                            ↓
                          </Button>
                          <Button
                            htmlType="button"
                            className="mr-1"
                            disabled={index === ids.length - 1}
                            aria-label={(model?.display_name ?? "模型") + "置底"}
                            onClick={() => setPriority(modelRowId, ids.length)}
                          >
                            置底
                          </Button>
                          <Button
                            danger
                            htmlType="button"

                            onClick={() =>
                              update(ids.filter((id) => id !== modelRowId))
                            }
                          >
                            移除
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Select<string>
              aria-label="选择要加入的模型"

              value={String(pendingAdd)}
              onChange={(selectedValue) => setPendingAdd(selectedValue)}
            >
              <Select.Option value="">选择要加入的模型…</Select.Option>
              {unbound.map((model) => (
                <Select.Option key={model.id} value={String(model.id)}>
                  {model.display_name}
                  {model.enabled ? "" : "（停用）"} ·{" "}
                  {model.provider_name ?? "—"}
                </Select.Option>
              ))}
            </Select>
            <Button
              htmlType="button"

              disabled={active.binding_available === false || pendingAdd === "" || ids.length >= maxBindings}
              onClick={add}
            >
              添加为备选
            </Button>
            <span className="text-[13px] text-slate-400">
              最多 {maxBindings} 个
            </span>

            <div className="ml-auto flex gap-2">
              <Button
                type="primary"
                htmlType="button"

                disabled={
                  busy ||
                  !dirty ||
                  !withinNumericRule(limit, fields.failover_limit) ||
                  !withinNumericRule(total, fields.max_total_requests)
                }
                onClick={save}
              >
                保存
              </Button>
              <Button
                htmlType="button"

                disabled={busy || !dirty}
                onClick={() => setDraft(null)}
              >
                放弃改动
              </Button>
            </div>
          </div>
        </fieldset>
      </ConfigProvider>
    </section>
  );
}
