"use client";
import { Button, Tabs } from "antd";

/**
 * 模型管理页容器：一次取齐供应商、模型、功能绑定三份数据（设计文档 12 第 8 节）。
 *
 * 三份数据互相引用（模型属于供应商、绑定指向模型），分开刷新会出现
 * "模型列表里已有、绑定下拉里还没有"的中间态，所以任何写操作后统一重取。
 *
 * 页头交给 PageShell：这一页和项目列表、配置中心是同一个骨架，
 * 各写一套页头迟早会分叉成"看起来像两个产品"。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { PageShell } from "@/components/PageShell";
import { ConfigWorkspace } from "@/components/config/ConfigCenter";
import {
  getLlmSettings,
  listFeatures,
  listModels,
  listProviders,
} from "@/lib/api/llm";
import { message } from "@/lib/llm/format";
import type {
  LlmFeature,
  LlmModel,
  LlmProvider,
  LlmSettings,
} from "@/types/llm";

import { FeatureBindingsPanel } from "./FeatureBindingsPanel";
import { ModelsPanel } from "./ModelsPanel";
import { ProvidersPanel } from "./ProvidersPanel";
import { CallLogsPanel } from "./CallLogsPanel";

type LoadState = "loading" | "ready" | "error";

export function ModelSettings() {
  const [section, setSection] = useState("providers");
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [models, setModels] = useState<LlmModel[]>([]);
  const [features, setFeatures] = useState<LlmFeature[]>([]);
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const loadSequence = useRef(0);

  const reload = useCallback(async () => {
    const sequence = ++loadSequence.current;
    const [nextProviders, nextModels, nextFeatures, nextSettings] =
      await Promise.all([
        listProviders(),
        listModels(),
        listFeatures(),
        getLlmSettings(),
      ]);
    // 测试轮询与保存后的刷新可能重叠，旧快照不能覆盖刚保存的状态。
    if (sequence !== loadSequence.current) return;
    setProviders(nextProviders);
    setModels(nextModels);
    setFeatures(nextFeatures);
    setSettings(nextSettings);
  }, []);

  useEffect(() => {
    let alive = true;
    reload()
      .then(() => {
        if (!alive) return;
        setState("ready");
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!alive) return;
        setError(message(caught, "加载模型配置失败"));
        setState("error");
      });
    return () => {
      alive = false;
    };
  }, [reload]);

  // 刷新失败时不把已经渲染好的面板收回去：能看旧数据总比看一片空白强，
  // 错误挂在面板上方，用户自己决定要不要重试。
  const refresh = () =>
    void reload()
      .then(() => setError(null))
      .catch((caught: unknown) => setError(message(caught, "刷新失败")));

  const retry = () => {
    setState("loading");
    setError(null);
    void reload()
      .then(() => setState("ready"))
      .catch((caught: unknown) => {
        setError(message(caught, "加载模型配置失败"));
        setState("error");
      });
  };

  return (
    <PageShell
      breadcrumb={[
        <span>设置</span>,
        <span className="text-slate-600">模型管理</span>,
      ]}
      eyebrow="设置 · 模型"
      title="模型管理"
      description="配置模型能力、调用顺序与预算，查看综合分析和知识检索的调用记录。"
      actions={
        <Button htmlType="button" onClick={refresh}>
          刷新
        </Button>
      }
    >
      {state === "loading" && (
        <p className="text-[14px] text-slate-500">正在加载模型配置…</p>
      )}

      {state === "error" && (
        <div className="border border-rose-200 bg-rose-50 px-4 py-3 text-[14px] text-rose-700">
          <p>{error ?? "加载失败"}</p>
          <p className="mt-1 text-[13px] text-rose-600">
            暂时无法获取模型配置，请确认服务可用后重试。
          </p>
          <Button htmlType="button" className={" mt-2"} onClick={retry}>
            重试
          </Button>
        </div>
      )}

      {state === "ready" && error !== null && (
        <div className="border border-rose-200 bg-rose-50 px-4 py-3 text-[14px] text-rose-700">
          {error}
        </div>
      )}

      {state === "ready" && settings && (
        <Tabs
          className="page-tabs"
          activeKey={section}
          onChange={setSection}
          destroyOnHidden={false}
          items={[
            {
              key: "providers",
              label: `连接供应商 (${providers.length})`,
              forceRender: true,
              children: (
                <ProvidersPanel
                  providers={providers}
                  profiles={settings.adapter_profiles}
                  secretReady={settings.secret_key_ready}
                  onChanged={reload}
                />
              ),
            },
            {
              key: "models",
              label: `管理模型 (${models.length})`,
              forceRender: true,
              children: (
                <ModelsPanel
                  providers={providers}
                  models={models}
                  profiles={settings.adapter_profiles}
                  fields={settings.model_fields}
                  onChanged={reload}
                />
              ),
            },
            {
              key: "bindings",
              label: "分配功能",
              forceRender: true,
              children: (
                <FeatureBindingsPanel
                  features={features}
                  models={models}
                  fields={settings.feature_fields}
                  maximumBindings={settings.max_bindings}
                  onChanged={reload}
                />
              ),
            },
            {
              key: "runtime",
              label: "分析参数",
              children: <ConfigWorkspace scope="models" />,
            },
            {
              key: "calls",
              label: "调用记录",
              forceRender: true,
              children: (
                <CallLogsPanel
                  active={section === "calls"}
                  features={features}
                  models={models}
                />
              ),
            },
          ]}
        />
      )}
    </PageShell>
  );
}
