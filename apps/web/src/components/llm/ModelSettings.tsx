"use client";

/**
 * 模型管理页容器：一次取齐供应商、模型、功能绑定三份数据（设计文档 12 第 8 节）。
 *
 * 三份数据互相引用（模型属于供应商、绑定指向模型），分开刷新会出现
 * "模型列表里已有、绑定下拉里还没有"的中间态，所以任何写操作后统一重取。
 */

import { useCallback, useEffect, useState } from "react";

import { AppNav } from "@/components/AppNav";
import { listFeatures, listModels, listProviders } from "@/lib/api/llm";
import { message } from "@/lib/llm/format";
import type { LlmFeature, LlmModel, LlmProvider } from "@/types/llm";

import { FeatureBindingsPanel } from "./FeatureBindingsPanel";
import { ModelsPanel } from "./ModelsPanel";
import { ProvidersPanel } from "./ProvidersPanel";
import { BUTTON_CLASS } from "./ui";

type LoadState = "loading" | "ready" | "error";

export function ModelSettings() {
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [models, setModels] = useState<LlmModel[]>([]);
  const [features, setFeatures] = useState<LlmFeature[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [nextProviders, nextModels, nextFeatures] = await Promise.all([
      listProviders(),
      listModels(),
      listFeatures(),
    ]);
    setProviders(nextProviders);
    setModels(nextModels);
    setFeatures(nextFeatures);
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

  const refresh = () => {
    void reload().catch((caught: unknown) => setError(message(caught, "刷新失败")));
  };

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
        <AppNav />
        <span className="text-sm text-slate-500">模型管理</span>
        <button type="button" className={BUTTON_CLASS + " ml-auto"} onClick={refresh}>
          刷新
        </button>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-4 p-4">
        {state === "loading" && <p className="text-sm text-slate-500">正在加载模型配置…</p>}

        {state === "error" && (
          <div className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {error ?? "加载失败"}
          </div>
        )}

        {state === "ready" && (
          <>
            <ProvidersPanel providers={providers} onChanged={reload} />
            <ModelsPanel providers={providers} models={models} onChanged={reload} />
            <FeatureBindingsPanel features={features} models={models} onChanged={reload} />
          </>
        )}
      </main>
    </div>
  );
}