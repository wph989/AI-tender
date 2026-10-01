"use client";

/**
 * 模型管理页容器：一次取齐供应商、模型、功能绑定三份数据（设计文档 12 第 8 节）。
 *
 * 三份数据互相引用（模型属于供应商、绑定指向模型），分开刷新会出现
 * "模型列表里已有、绑定下拉里还没有"的中间态，所以任何写操作后统一重取。
 *
 * 页头交给 PageShell：这一页和项目列表、配置中心是同一个骨架，
 * 各写一套页头迟早会分叉成"看起来像两个产品"。
 */

import { useCallback, useEffect, useState } from "react";

import { PageShell } from "@/components/PageShell";
import { BUTTON_CLASS, SETTINGS_GRID_CLASS } from "@/components/ui";
import { listFeatures, listModels, listProviders } from "@/lib/api/llm";
import { message } from "@/lib/llm/format";
import type { LlmFeature, LlmModel, LlmProvider } from "@/types/llm";

import { FeatureBindingsPanel } from "./FeatureBindingsPanel";
import { ModelsPanel } from "./ModelsPanel";
import { ProvidersPanel } from "./ProvidersPanel";

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
      breadcrumb={[<span>设置</span>, <span className="text-slate-600">模型管理</span>]}
      eyebrow="设置 · 模型"
      title="模型管理"
      description="供应商、模型、功能绑定三者互相引用：模型属于供应商，功能绑定又指向模型。测试会真实发一次请求，用来判断这条链路到底通不通。"
      actions={
        <button type="button" className={BUTTON_CLASS} onClick={refresh}>
          刷新
        </button>
      }
    >
      {state === "loading" && (
        <p className="text-[14px] text-slate-500">正在加载模型配置…</p>
      )}

      {state === "error" && (
        <div className="border border-rose-200 bg-rose-50 px-4 py-3 text-[14px] text-rose-700">
          <p>{error ?? "加载失败"}</p>
          <p className="mt-1 text-[13px] text-rose-600">
            数据来自后端 /api/v1/llm，多半是服务没起来。确认后点下面的重试。
          </p>
          <button type="button" className={BUTTON_CLASS + " mt-2"} onClick={retry}>
            重试
          </button>
        </div>
      )}

      {state === "ready" && error !== null && (
        <div className="border border-rose-200 bg-rose-50 px-4 py-3 text-[14px] text-rose-700">
          {error}
        </div>
      )}

      {state === "ready" && (
        /*
         * 超宽屏（≥1536px）分两栏：供应商的表格要横跨一整行（Base URL 与四个行内动作），
         * 模型表与功能绑定表并排——它们被压到 ~680px 时只会让「参数」「最近测试」两列折行，
         * 仍然读得下去；而供应商表这样并排会连操作按钮都换行。
         */
        <div className={SETTINGS_GRID_CLASS}>
          <div className="2xl:col-span-2">
            <ProvidersPanel providers={providers} onChanged={reload} />
          </div>
          <ModelsPanel providers={providers} models={models} onChanged={reload} />
          <FeatureBindingsPanel features={features} models={models} onChanged={reload} />
        </div>
      )}
    </PageShell>
  );
}
