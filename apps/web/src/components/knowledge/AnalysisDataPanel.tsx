"use client";

import { Alert, Button, Collapse, Drawer, Empty, Select, Space, Spin, Table, Tabs, Tag, Tree } from "antd";
import type { DataNode } from "antd/es/tree";
import { useCallback, useEffect, useRef, useState } from "react";
import { knowledgeRequest } from "@/lib/api/knowledge";
import { scopeLabel } from "@/lib/analysis/scope";
import { ResearchGaps } from "./ResearchGaps";
import type {
  AnalysisContext, AnalysisDataSnapshot, AnalysisReport, AnalysisScope, BusinessRecord, Citation,
} from "@/types/knowledge";

const readinessLabels = { usable: "依据可用", partial: "有待核对事项", unavailable: "依据不足" };
const coverageLabels: Record<string, string> = {
  extracted: "已汇总", searched_not_found: "本次检索未找到", pending: "尚未核对完整",
  not_applicable: "已确认不适用", unchecked: "未检查",
};

interface Props {
  report: AnalysisReport;
  onLocate: (citation: Citation) => void;
}

/** 预览固定一个标段；切换标段或报告时丢弃旧请求，避免旧依据覆盖新选择。 */
export function AnalysisDataPanel({ report, onLocate }: Props) {
  const [snapshot, setSnapshot] = useState<AnalysisDataSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lotId, setLotId] = useState<number>();
  const [open, setOpen] = useState(false);
  const [context, setContext] = useState<AnalysisContext | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dataAbort = useRef<AbortController | null>(null);
  const previewAbort = useRef<AbortController | null>(null);
  const terminal = !["waiting", "pending", "running"].includes(report.status);

  const reload = useCallback(async () => {
    dataAbort.current?.abort();
    const abort = new AbortController();
    dataAbort.current = abort;
    setLoading(true);
    setError(null);
    try {
      const data = await knowledgeRequest<AnalysisDataSnapshot>(
        `/analysis/reports/${report.id}/data`, "GET", undefined, abort.signal,
      );
      if (!abort.signal.aborted) {
        setSnapshot(data);
        const unresolvedLots = data.data.gaps.some((gap) => gap.code === "lot_catalog_unknown"
          || (gap.code === "scope_unknown" && gap.scope.lot_refs.length > 0));
        // 只识别到一个标段、目录却未核对完整时，仍须用户明确选择。
        setLotId(data.data.lots.length === 1 && !unresolvedLots ? data.data.lots[0]?.lot_id : undefined);
      }
    } catch (reason) {
      if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : "投标要求加载失败");
    } finally {
      if (!abort.signal.aborted) setLoading(false);
    }
  }, [report.id]);

  useEffect(() => {
    setSnapshot(null);
    // 新一轮快照加载完成前不能沿用上轮标段，单标段默认值由 reload 核实后设置。
    setLotId(undefined);
    setContext(null);
    setOpen(false);
    setPreviewError(null);
    setBusy(false);
    previewAbort.current?.abort();
    if (terminal) void reload();
    return () => { dataAbort.current?.abort(); previewAbort.current?.abort(); };
  }, [reload, terminal, report.finished_at, report.stale]);

  function scopeLabelFor(scope: AnalysisScope) {
    if (scope.kind === "unknown") return "适用标段待核对";
    return scopeLabel(scope, (id) =>
      snapshot?.data.lots.find((lot) => lot.lot_id === id)?.title);
  }

  function citations(record: BusinessRecord) {
    return <Space wrap>{record.citations.map((ref, index) => (
      <Button key={`${ref.element_id}-${index}`} type="link" size="small" onClick={() => {
        previewAbort.current?.abort(); setBusy(false); setOpen(false); onLocate(ref);
      }}>原文{record.citations.length > 1 ? index + 1 : ""}</Button>
    ))}</Space>;
  }

  function recordsTable(records: BusinessRecord[]) {
    return <Table<BusinessRecord> size="small" rowKey="id" dataSource={records}
      pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
      scroll={{ x: 550 }} columns={[
        { title: "事项", dataIndex: "title", width: 135 },
        { title: "依据内容", render: (_, row) => <div className="whitespace-pre-wrap">{row.text}{citations(row)}
          {row.structuring === "partial" && <Tag color="gold">部分条件待核对</Tag>}
          {Boolean(row.superseded_in?.length) && <Tag>部分范围已有修订</Tag>}
          {Boolean(row.conflicts_in?.length) && <Tag color="gold">存在待核对冲突</Tag>}</div> },
        { title: "适用范围", width: 115, render: (_, row) => scopeLabelFor(row.scope) },
      ]} />;
  }

  function tree(nodes: BusinessRecord[]): DataNode[] {
    const ids = new Set(nodes.map((node) => node.id));
    const children = new Map<string | null, BusinessRecord[]>();
    for (const node of nodes) {
      const parent = node.parent_id && ids.has(node.parent_id) ? node.parent_id : null;
      children.set(parent, [...(children.get(parent) ?? []), node]);
    }
    const make = (parent: string | null, ancestors: Set<string>): DataNode[] =>
      (children.get(parent) ?? []).filter((node) => !ancestors.has(node.id))
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)).map((node) => ({
        key: node.id,
        title: <span>{node.title} <span className="text-xs text-slate-500">{scopeLabelFor(node.scope)}</span>{citations(node)}</span>,
        children: make(node.id, new Set([...ancestors, node.id])),
      }));
    return make(null, new Set());
  }

  async function preview(append = false) {
    if (!snapshot) return;
    previewAbort.current?.abort();
    const abort = new AbortController();
    previewAbort.current = abort;
    setBusy(true);
    setPreviewError(null);
    try {
      const next = await knowledgeRequest<AnalysisContext>(`/analysis/reports/${report.id}/context`, "POST", {
        snapshot_id: snapshot.snapshot_id, purpose: "outline", lot_id: lotId ?? null,
        offset: append ? context?.next_offset ?? 0 : 0, limit: 100,
      }, abort.signal);
      if (!abort.signal.aborted) setContext((old) => append && old
        ? { ...next, requirements: [...old.requirements, ...next.requirements] } : next);
    } catch (reason) {
      if (!abort.signal.aborted) setPreviewError(reason instanceof Error ? reason.message : "投标要求加载失败");
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }

  if (!terminal) return <Alert className="my-3" type="info" title="分析结束后可查看投标要求汇总，已有结果会持续保存。" />;
  const data = snapshot?.data;
  return <section className="my-3" aria-label="投标要求汇总">
    {loading && <Spin size="small" description="正在加载投标要求" />}
    {error && <Alert type="warning" title={error} action={<Button onClick={() => void reload()}>重试</Button>} />}
    {data && <Collapse items={[{
      key: "data", label: <Space wrap><strong>投标要求汇总</strong>
        <Tag color={data.readiness === "usable" ? "green" : "gold"}>{readinessLabels[data.readiness]}</Tag>
        <span>{data.requirements.length} 项要求 · {data.gaps.length} 项待核对</span></Space>,
      children: <>
        <p className="mb-3 text-sm text-slate-500">汇总各专题已核实的要求，供编写投标文件时参考。</p>
        <Space className="mb-3" wrap>
          <Button type="primary" disabled={report.stale || snapshot.stale || data.readiness === "unavailable"}
            onClick={() => {
              previewAbort.current?.abort(); setBusy(false);
              setContext(null); setPreviewError(null); setOpen(true);
            }}>按标段查看要求</Button>
          <span className="text-sm text-slate-500">下方显示全部标段，可选择一个标段查看适用要求。</span>
        </Space>
        <Tabs items={[
          { key: "requirements", label: "要求与项目信息", children: recordsTable([...data.requirements, ...data.facts]) },
          { key: "format", label: "格式与材料", children: data.format_nodes.length
            ? <Tree showLine defaultExpandAll treeData={tree(data.format_nodes)} /> : <Empty description="暂无已核实的投标文件格式要求" /> },
          { key: "gaps", label: `待核对事项 ${data.gaps.length}`, children: data.gaps.length
            ? <ResearchGaps gaps={data.gaps.map((gap, index) => ({
              key: String(index), detail: gap.detail, scopeLabel: scopeLabelFor(gap.scope),
            }))} /> : <p>当前没有已登记的待核对事项。</p> },
          { key: "coverage", label: "专题检查进度", children: <Table size="small" rowKey={(row) => `${row.title}-${JSON.stringify(row.scope)}`}
            dataSource={data.coverage} pagination={{ pageSize: 10, showSizeChanger: false }} columns={[
              { title: "主题", dataIndex: "title" },
              { title: "状态", render: (_, row) => coverageLabels[row.status] ?? row.status },
              { title: "范围", render: (_, row) => scopeLabelFor(row.scope) },
              { title: "说明", dataIndex: "detail" },
            ]} /> },
        ]} />
      </>,
    }]} />}
    <Drawer title="按标段查看投标要求" open={open} size={760} onClose={() => {
      previewAbort.current?.abort(); setBusy(false); setOpen(false);
    }}>
      <Space className="mb-4" wrap>
        {data && data.lots.length > 0 ? <Select aria-label="投标标段" placeholder="请选择一个投标标段"
          value={lotId} style={{ minWidth: 240 }} options={data.lots.map((lot) => ({ value: lot.lot_id, label: lot.title }))}
          onChange={(value: number) => {
            previewAbort.current?.abort(); setBusy(false); setLotId(value); setContext(null); setPreviewError(null);
          }} /> : <Tag>当前项目</Tag>}
        <Button type="primary" aria-label="查看要求" loading={busy}
          disabled={!snapshot || loading || Boolean(data?.lots.length && !lotId)}
          onClick={() => void preview()}>查看要求</Button>
      </Space>
      {previewError && <Alert className="mb-3" type="error" title={previewError} />}
      {context && <>
        <Alert className="mb-3" type={context.readiness === "usable" ? "success" : "warning"}
          title={readinessLabels[context.readiness]} description={`共 ${context.total_requirements} 项适用要求。${context.readiness === "usable" ? "" : "仍有内容待核对，请结合原文使用。"}`} />
        {context.facts.length > 0 && <><h3 className="my-3 font-medium">项目信息</h3>{recordsTable(context.facts)}</>}
        <h3 className="my-3 font-medium">适用要求</h3>
        {recordsTable(context.requirements)}
        {context.next_offset !== null && <Button className="my-3" loading={busy} onClick={() => void preview(true)}>加载更多要求</Button>}
        {context.format_nodes.length > 0 && <Tree className="my-3" showLine defaultExpandAll treeData={tree(context.format_nodes)} />}
        {context.unresolved.length > 0 && <><h3 className="my-3 font-medium">适用标段或条款版本待核对</h3>{recordsTable(context.unresolved)}</>}
        <ResearchGaps gaps={context.gaps.map((gap, index) => ({
          key: String(index), detail: gap.detail, scopeLabel: scopeLabelFor(gap.scope),
        }))} />
      </>}
    </Drawer>
  </section>;
}
