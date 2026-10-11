"use client";

import { Alert, Button, Collapse, Drawer, Empty, Select, Space, Spin, Table, Tabs, Tag, Tree } from "antd";
import type { DataNode } from "antd/es/tree";
import { useCallback, useEffect, useRef, useState } from "react";
import { knowledgeRequest } from "@/lib/api/knowledge";
import type {
  AnalysisContext, AnalysisDataSnapshot, AnalysisReport, AnalysisScope, BusinessRecord, Citation,
} from "@/types/knowledge";

const readinessLabels = { usable: "依据可用", partial: "有待核对事项", unavailable: "依据不足" };
const coverageLabels: Record<string, string> = {
  extracted: "已提取", searched_not_found: "本次检索未找到", pending: "待补读",
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
      if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : "依据加载失败");
    } finally {
      if (!abort.signal.aborted) setLoading(false);
    }
  }, [report.id]);

  useEffect(() => {
    setSnapshot(null);
    setContext(null);
    setOpen(false);
    setPreviewError(null);
    setBusy(false);
    previewAbort.current?.abort();
    if (terminal) void reload();
    return () => { dataAbort.current?.abort(); previewAbort.current?.abort(); };
  }, [reload, terminal, report.finished_at, report.stale]);

  function scopeLabel(scope: AnalysisScope) {
    if (scope.kind === "common") return "公共要求";
    if (scope.kind === "unknown") return "归属待确认";
    return scope.lot_ids.map((id) => snapshot?.data.lots.find((lot) => lot.lot_id === id)?.title ?? "标段待确认").join("、");
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
        { title: "适用范围", width: 115, render: (_, row) => scopeLabel(row.scope) },
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
        title: <span>{node.title} <span className="text-xs text-slate-500">{scopeLabel(node.scope)}</span>{citations(node)}</span>,
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
      if (!abort.signal.aborted) setPreviewError(reason instanceof Error ? reason.message : "编制依据加载失败");
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }

  if (!terminal) return <Alert className="my-3" type="info" title="分析结束后可查看本轮编制依据，已核实成果会持续保存。" />;
  const data = snapshot?.data;
  return <section className="my-3" aria-label="编制依据与待核对事项">
    {loading && <Spin size="small" description="正在加载编制依据" />}
    {error && <Alert type="warning" title={error} action={<Button onClick={() => void reload()}>重试</Button>} />}
    {data && <Collapse items={[{
      key: "data", label: <Space wrap><strong>编制依据与待核对事项</strong>
        <Tag color={data.readiness === "usable" ? "green" : "gold"}>{readinessLabels[data.readiness]}</Tag>
        <span>{data.requirements.length} 项要求 · {data.gaps.length} 项待核对</span></Space>,
      children: <>
        <Space className="mb-3" wrap>
          <Button type="primary" disabled={report.stale || snapshot.stale || data.readiness === "unavailable"}
            onClick={() => {
              previewAbort.current?.abort(); setBusy(false);
              setContext(null); setPreviewError(null); setOpen(true);
            }}>编制依据预览</Button>
          <span className="text-sm text-slate-500">此处浏览全部标段；编制时仅使用选定的一个标段。</span>
        </Space>
        <Tabs items={[
          { key: "requirements", label: "要求与项目事实", children: recordsTable([...data.requirements, ...data.facts]) },
          { key: "format", label: "格式与材料", children: data.format_nodes.length
            ? <Tree showLine defaultExpandAll treeData={tree(data.format_nodes)} /> : <Empty description="暂无已核实的格式节点" /> },
          { key: "gaps", label: `待核对事项 ${data.gaps.length}`, children: data.gaps.length
            ? <ul className="space-y-2">{data.gaps.map((gap, index) => <li key={index}>
              <Tag>{scopeLabel(gap.scope)}</Tag>{gap.detail}</li>)}</ul> : <p>当前没有已登记的待核对事项。</p> },
          { key: "coverage", label: "专题核对", children: <Table size="small" rowKey={(row) => `${row.title}-${JSON.stringify(row.scope)}`}
            dataSource={data.coverage} pagination={{ pageSize: 10, showSizeChanger: false }} columns={[
              { title: "主题", dataIndex: "title" },
              { title: "状态", render: (_, row) => coverageLabels[row.status] ?? row.status },
              { title: "范围", render: (_, row) => scopeLabel(row.scope) },
              { title: "说明", dataIndex: "detail" },
            ]} /> },
        ]} />
      </>,
    }]} />}
    <Drawer title="编制依据预览" open={open} size={760} onClose={() => {
      previewAbort.current?.abort(); setBusy(false); setOpen(false);
    }}>
      <Space className="mb-4" wrap>
        {data && data.lots.length > 0 ? <Select aria-label="编制标段" placeholder="请选择一个编制标段"
          value={lotId} style={{ minWidth: 240 }} options={data.lots.map((lot) => ({ value: lot.lot_id, label: lot.title }))}
          onChange={(value: number) => {
            previewAbort.current?.abort(); setBusy(false); setLotId(value); setContext(null); setPreviewError(null);
          }} /> : <Tag>项目级编制</Tag>}
        <Button type="primary" loading={busy} disabled={Boolean(data?.lots.length && !lotId)}
          onClick={() => void preview()}>加载编制依据</Button>
      </Space>
      {previewError && <Alert className="mb-3" type="error" title={previewError} />}
      {context && <>
        <Alert className="mb-3" type={context.readiness === "usable" ? "success" : "warning"}
          title={readinessLabels[context.readiness]} description={`共 ${context.total_requirements} 项适用要求。部分可用的依据可辅助编制草稿，不能视为完整检查结论。`} />
        {context.facts.length > 0 && <><h3 className="my-3 font-medium">项目事实</h3>{recordsTable(context.facts)}</>}
        <h3 className="my-3 font-medium">适用要求</h3>
        {recordsTable(context.requirements)}
        {context.next_offset !== null && <Button className="my-3" loading={busy} onClick={() => void preview(true)}>加载更多要求</Button>}
        {context.format_nodes.length > 0 && <Tree className="my-3" showLine defaultExpandAll treeData={tree(context.format_nodes)} />}
        {context.unresolved.length > 0 && <><h3 className="my-3 font-medium">归属或效力待确认</h3>{recordsTable(context.unresolved)}</>}
        {context.gaps.length > 0 && <><h3 className="my-3 font-medium">当前范围的待核对事项</h3>
          <ul className="space-y-2">{context.gaps.map((gap, index) => <li key={index}>{gap.detail}</li>)}</ul></>}
      </>}
    </Drawer>
  </section>;
}
