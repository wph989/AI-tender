"use client";

import { useEffect, useRef, useState } from "react";
import { listCalls } from "@/lib/api/llm";
import { formatTime, message } from "@/lib/llm/format";
import type { LlmCall, LlmFeature, LlmModel } from "@/types/llm";
import { BUTTON_CLASS, SELECT_CLASS } from "./ui";

const statusNames: Record<string, string> = {
  ok: "成功",
  error: "失败",
  running: "进行中",
  unknown: "结果未知",
  unsupported: "不支持",
};

export function CallLogsPanel({
  active,
  features,
  models,
}: {
  active: boolean;
  features: LlmFeature[];
  models: LlmModel[];
}) {
  const [filters, setFilters] = useState({
    feature_key: "",
    model_id: "",
    status: "",
    offset: 0,
  });
  const [data, setData] = useState<{ items: LlmCall[]; total: number } | null>(
    null,
  );
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chain, setChain] = useState<{ id: string; items: LlmCall[] } | null>(
    null,
  );
  const [chainBusy, setChainBusy] = useState(false);
  const chainRequest = useRef(0);

  useEffect(() => {
    if (!active) return;
    // 切换筛选后忽略旧响应，避免较慢的上一页覆盖当前结果。
    let canceled = false;
    setBusy(true);
    setError(null);
    setData(null);
    void listCalls(filters)
      .then((set) => {
        if (!canceled) setData(set);
      })
      .catch((e) => {
        if (!canceled) setError(message(e, "加载调用记录失败"));
      })
      .finally(() => {
        if (!canceled) setBusy(false);
      });
    return () => {
      canceled = true;
    };
  }, [active, filters, refresh]);

  const showChain = async (id: string) => {
    const request = ++chainRequest.current;
    setChain({ id, items: [] });
    setChainBusy(true);
    setError(null);
    try {
      const result = await listCalls({ invocation_id: id, offset: 0 });
      if (request === chainRequest.current)
        setChain({ id, items: result.items });
    } catch (e) {
      if (request === chainRequest.current)
        setError(message(e, "加载调用链失败"));
    } finally {
      if (request === chainRequest.current) setChainBusy(false);
    }
  };

  return (
    <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap justify-between gap-3">
        <div>
          <h2 className="font-display text-[19px] font-semibold">调用记录</h2>
          <p className="mt-1 text-sm text-slate-500">
            查看实际请求与失败链。未返回的用量显示为“—”，不保存提示词和响应正文。
          </p>
        </div>
        <button
          className={BUTTON_CLASS}
          disabled={busy}
          onClick={() => setRefresh((value) => value + 1)}
        >
          刷新记录
        </button>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <select
          aria-label="按调用功能筛选"
          className={SELECT_CLASS}
          value={filters.feature_key}
          onChange={(e) =>
            setFilters({ ...filters, feature_key: e.target.value, offset: 0 })
          }
        >
          <option value="">全部功能（含测试）</option>
          {features.map((f) => (
            <option key={f.key} value={f.key}>
              {f.name}
            </option>
          ))}
        </select>
        <select
          aria-label="按调用模型筛选"
          className={SELECT_CLASS}
          value={filters.model_id}
          onChange={(e) =>
            setFilters({ ...filters, model_id: e.target.value, offset: 0 })
          }
        >
          <option value="">全部模型（含已删除）</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name}
            </option>
          ))}
        </select>
        <select
          aria-label="按调用状态筛选"
          className={SELECT_CLASS}
          value={filters.status}
          onChange={(e) =>
            setFilters({ ...filters, status: e.target.value, offset: 0 })
          }
        >
          <option value="">全部状态</option>
          {Object.entries(statusNames).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-rose-700">
          {error}
        </p>
      )}
      {busy && (
        <p role="status" className="mt-4 text-sm text-slate-500">
          正在加载调用记录…
        </p>
      )}
      {data && (
        <>
          <div className="mt-4 space-y-3">
            {data.items.map((call) => (
              <CallItem
                key={call.id}
                call={call}
                feature={features.find((f) => f.key === call.feature_key)?.name}
                onChain={showChain}
              />
            ))}
          </div>
          {!data.items.length && (
            <p className="mt-4 text-sm text-slate-500">
              暂无符合条件的调用记录。
            </p>
          )}
          <div className="mt-4 flex flex-wrap items-center justify-end gap-3 text-sm">
            <span>
              共 {data.total} 条 · 第 {Math.floor(filters.offset / 25) + 1} 页
            </span>
            <button
              className={BUTTON_CLASS}
              disabled={busy || filters.offset === 0}
              onClick={() =>
                setFilters({
                  ...filters,
                  offset: Math.max(0, filters.offset - 25),
                })
              }
            >
              上一页
            </button>
            <button
              className={BUTTON_CLASS}
              disabled={busy || filters.offset + 25 >= data.total}
              onClick={() =>
                setFilters({ ...filters, offset: filters.offset + 25 })
              }
            >
              下一页
            </button>
          </div>
        </>
      )}
      {chain && (
        <div
          className="mt-5 rounded-xl border border-violet-200 bg-violet-50/30 p-4"
          aria-label="完整调用链"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">请求顺序</h3>
            <button
              className={BUTTON_CLASS}
              onClick={() => {
                ++chainRequest.current;
                setChain(null);
              }}
            >
              关闭调用链
            </button>
          </div>
          <p className="mt-1 break-all text-xs text-slate-500">{chain.id}</p>
          {chainBusy ? (
            <p className="mt-3 text-sm">正在加载…</p>
          ) : (
            <div className="mt-3 space-y-3">
              {chain.items.map((call) => (
                <CallItem key={call.id} call={call} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function CallItem({
  call,
  feature,
  onChain,
}: {
  call: LlmCall;
  feature?: string;
  onChain?: (id: string) => void;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <div className="flex flex-wrap justify-between gap-2">
        <strong className="break-all">
          {call.display_name ?? "供应商目录"} ·{" "}
          {call.provider_name ?? "未知供应商"}
        </strong>
        <span>{statusNames[call.status] ?? call.status}</span>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {feature ?? call.feature_key ?? "管理测试"} ·{" "}
        {formatTime(call.created_at)} · {call.latency_ms} ms
      </p>
      {call.request_ordinal !== null && (
        <p className="mt-2">
          请求 #{call.request_ordinal} · 候选 {call.candidate_ordinal} ·{" "}
          {call.retry_ordinal === 0
            ? "首次请求"
            : `额外重试 ${call.retry_ordinal}`}
        </p>
      )}
      <p className="mt-2 text-xs text-slate-500">
        输入 tokens {call.prompt_tokens ?? "—"} · 输出 tokens{" "}
        {call.completion_tokens ?? "—"} · 向量 {call.vector_count ?? "—"} ·
        重排文档 {call.document_count ?? "—"} · 图片 {call.image_count ?? "—"}
      </p>
      {call.status === "unknown" && (
        <p className="mt-2 text-amber-700">
          结果未知，供应商可能仍在处理，费用尚未确认。
        </p>
      )}
      {call.error_message && (
        <p className="mt-2 break-words text-rose-700">{call.error_message}</p>
      )}
      {onChain && call.invocation_id && (
        <button
          className={BUTTON_CLASS + " mt-3"}
          onClick={() => onChain(call.invocation_id!)}
        >
          查看调用链
        </button>
      )}
    </article>
  );
}
