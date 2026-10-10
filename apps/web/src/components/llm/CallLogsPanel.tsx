"use client";
import { Alert, Button, Drawer, Select, Spin, Table, Tag } from "antd";

import { useEffect, useRef, useState } from "react";
import { listCalls } from "@/lib/api/llm";
import { formatTime, message } from "@/lib/llm/format";
import type { LlmCall, LlmFeature, LlmModel } from "@/types/llm";

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
  const [chainError, setChainError] = useState<string | null>(null);
  const [chainBusy, setChainBusy] = useState(false);
  const chainRequest = useRef(0);

  useEffect(() => {
    if (!active) return;
    // 切换筛选后忽略旧响应，避免较慢的上一页覆盖当前结果。
    let canceled = false;
    setBusy(true);
    setError(null);

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
    setChainError(null);
    try {
      // 后端单页最多 25 条；调用链需继续取完，不能把第一页误称为完整记录。
      const items: LlmCall[] = [];
      let total = 1;
      while (items.length < total && request === chainRequest.current) {
        const result = await listCalls({
          invocation_id: id,
          offset: items.length,
        });
        total = result.total;
        if (!result.items.length) break;
        items.push(...result.items);
      }
      if (request === chainRequest.current) setChain({ id, items });
    } catch (e) {
      if (request === chainRequest.current)
        setChainError(message(e, "加载调用链失败"));
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
        <Button
          htmlType="submit"

          disabled={busy}
          onClick={() => setRefresh((value) => value + 1)}
        >
          刷新记录
        </Button>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Select<string>
          aria-label="按调用功能筛选"

          value={String(filters.feature_key)}
          onChange={(selectedValue) =>
            setFilters({ ...filters, feature_key: selectedValue, offset: 0 })
          }
        >
          <Select.Option value="">全部功能（含测试）</Select.Option>
          {features.map((f) => (
            <Select.Option key={f.key} value={String(f.key)}>
              {f.name}
            </Select.Option>
          ))}
        </Select>
        <Select<string>
          aria-label="按调用模型筛选"

          value={String(filters.model_id)}
          onChange={(selectedValue) =>
            setFilters({ ...filters, model_id: selectedValue, offset: 0 })
          }
        >
          <Select.Option value="">全部模型（含已删除）</Select.Option>
          {models.map((m) => (
            <Select.Option key={m.id} value={String(m.id)}>
              {m.display_name}
            </Select.Option>
          ))}
        </Select>
        <Select<string>
          aria-label="按调用状态筛选"

          value={String(filters.status)}
          onChange={(selectedValue) =>
            setFilters({ ...filters, status: selectedValue, offset: 0 })
          }
        >
          <Select.Option value="">全部状态</Select.Option>
          {Object.entries(statusNames).map(([key, label]) => (
            <Select.Option key={key} value={String(key)}>
              {label}
            </Select.Option>
          ))}
        </Select>
      </div>
      {error && (
        <Alert
          className="my-4"
          type="error"
          showIcon
          title={error}
          action={
            <Button size="small" onClick={() => setRefresh((n) => n + 1)}>
              重试
            </Button>
          }
        />
      )}
      <Table<LlmCall>
        className="mt-4"
        rowKey="id"
        dataSource={data?.items ?? []}
        loading={busy}
        size="middle"
        scroll={{ x: 860 }}
        pagination={{
          current: Math.floor(filters.offset / 25) + 1,
          pageSize: 25,
          total: data?.total ?? 0,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条记录`,
          onChange: (page) =>
            setFilters({ ...filters, offset: (page - 1) * 25 }),
        }}
        expandable={{
          expandedRowRender: (call) => <CallItem call={call} />,
          columnTitle: "详情",
          columnWidth: 55,
        }}
        columns={[
          {
            title: "时间",
            dataIndex: "created_at",
            width: 180,
            render: (value: string) => formatTime(value),
          },
          {
            title: "模型 / 供应商",
            key: "model",
            width: 230,
            render: (_, call) => (
              <>
                <strong>{call.display_name ?? "供应商目录"}</strong>
                <p className="text-xs text-slate-500">
                  {call.provider_name ?? "未知供应商"}
                </p>
              </>
            ),
          },
          {
            title: "功能",
            key: "feature",
            width: 140,
            render: (_, call) =>
              features.find((f) => f.key === call.feature_key)?.name ??
              call.feature_key ??
              "管理测试",
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 100,
            render: (value: string) => (
              <Tag
                color={
                  value === "ok"
                    ? "success"
                    : value === "error"
                      ? "error"
                      : "default"
                }
              >
                {statusNames[value] ?? value}
              </Tag>
            ),
          },
          {
            title: "耗时",
            dataIndex: "latency_ms",
            width: 100,
            render: (value: number | null) =>
              value == null ? "—" : `${(value / 1000).toFixed(1)} 秒`,
          },
          {
            title: "操作",
            key: "actions",
            width: 125,
            render: (_, call) =>
              call.invocation_id ? (
                <Button
                  size="small"
                  onClick={() => void showChain(call.invocation_id!)}
                >
                  查看调用链
                </Button>
              ) : (
                "—"
              ),
          },
        ]}
      />
      <Drawer
        title="完整调用链"
        open={chain !== null}
        size={720}
        onClose={() => {
          ++chainRequest.current;
          setChain(null);
          setChainBusy(false);
        }}
        destroyOnHidden
      >
        <p className="mb-4 break-all text-xs text-slate-500">{chain?.id}</p>
        {chainError && (
          <Alert
            type="error"
            showIcon
            title={chainError}
            action={
              <Button
                size="small"
                onClick={() => chain && void showChain(chain.id)}
              >
                重试
              </Button>
            }
          />
        )}
        {chainBusy ? (
          <Spin tip="正在加载请求顺序">
            <div className="h-24" />
          </Spin>
        ) : (
          <div className="space-y-3">
            {chain?.items.map((call) => (
              <CallItem key={call.id} call={call} />
            ))}
          </div>
        )}
      </Drawer>
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
        <Button
          htmlType="submit"
          className={" mt-3"}
          onClick={() => onChain(call.invocation_id!)}
        >
          查看调用链
        </Button>
      )}
    </article>
  );
}
