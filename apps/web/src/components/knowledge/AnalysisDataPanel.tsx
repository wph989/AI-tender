"use client";

import { Alert, Button, Drawer, Select, Space, Table, Tag, Tree } from "antd";
import type { DataNode } from "antd/es/tree";
import { useEffect, useRef, useState } from "react";
import { knowledgeRequest } from "@/lib/api/knowledge";
import { scopeLabel } from "@/lib/analysis/scope";
import { ResearchGaps } from "./ResearchGaps";
import { EvidenceReferences } from "./EvidenceReferences";
import type {
  AnalysisContext, AnalysisDataSnapshot, AnalysisReport, AnalysisScope, BusinessRecord, Citation,
} from "@/types/knowledge";

const readinessLabels = { usable: "依据可用", partial: "有待核对事项", unavailable: "依据不足" };
interface Props {
  report: AnalysisReport;
  onLocate: (citation: Citation) => void;
  snapshot: AnalysisDataSnapshot | null;
  open: boolean;
  onClose: () => void;
}

/** 预览固定一个标段；切换标段或报告时丢弃旧请求，避免旧依据覆盖新选择。 */
export function AnalysisDataPanel({ report, onLocate, snapshot, open, onClose }: Props) {
  const [lotId, setLotId] = useState<number>();
  const [context, setContext] = useState<AnalysisContext | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const previewAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    // 新报告与新快照都要重新选择，不能让旧标段的结果覆盖新报告。
    previewAbort.current?.abort();
    setContext(null); setPreviewError(null); setBusy(false);
    const data = snapshot?.data;
    const unresolved = data?.gaps.some((gap) => gap.code === "lot_catalog_unknown"
      || (gap.code === "scope_unknown" && gap.scope.lot_refs.length > 0));
    setLotId(data?.lots.length === 1 && !unresolved ? data.lots[0]?.lot_id : undefined);
    return () => previewAbort.current?.abort();
  }, [report.id, snapshot?.snapshot_id]);
  useEffect(() => {
    if (!open) { previewAbort.current?.abort(); setBusy(false); }
  }, [open]);

  function scopeLabelFor(scope: AnalysisScope) {
    return scopeLabel(scope, (id) =>
      snapshot?.data.lots.find((lot) => lot.lot_id === id)?.title);
  }

  function citations(record: BusinessRecord) {
    return <EvidenceReferences refs={record.citations} onLocate={(ref) => {
      previewAbort.current?.abort(); setBusy(false); onClose(); onLocate(ref);
    }} />;
  }

  function recordsTable(records: BusinessRecord[]) {
    return <Table<BusinessRecord> size="small" rowKey="id" dataSource={records}
      pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
      scroll={{ x: 550 }} columns={[
        { title: "事项", dataIndex: "title", width: 135 },
        { title: "依据内容", render: (_, row) => <div className="whitespace-pre-wrap">{row.text}{citations(row)}
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
        title: <div><strong>{node.title}</strong> <span className="text-xs text-slate-500">{scopeLabelFor(node.scope)}</span>
          <p className="whitespace-pre-wrap">{node.text}</p>{citations(node)}</div>,
        children: make(node.id, new Set([...ancestors, node.id])),
      }));
    return make(null, new Set());
  }

  async function preview(append = false) {
    if (!snapshot || report.stale || snapshot.stale || snapshot.data.readiness === "unavailable") return;
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

  const data = snapshot?.data;
  return <Drawer title="按标段查看投标要求" open={open} size={760} onClose={onClose}>
      <p className="mb-3 text-sm text-slate-500">这里使用报告快照中已确认的标段范围。公共要求一并保留，范围未确认的条款单列。</p>
      <Space className="mb-4" wrap>
        {data && data.lots.length > 0 ? <Select aria-label="投标标段" placeholder="请选择一个投标标段"
          value={lotId} style={{ minWidth: 240 }} options={data.lots.map((lot) => ({ value: lot.lot_id, label: lot.title }))}
          onChange={(value: number) => {
            previewAbort.current?.abort(); setBusy(false); setLotId(value); setContext(null); setPreviewError(null);
          }} /> : <Tag>当前项目</Tag>}
        <Button type="primary" aria-label="查看要求" loading={busy}
          disabled={!snapshot || Boolean(data?.lots.length && !lotId) || report.stale || Boolean(snapshot?.stale) || data?.readiness === "unavailable"}
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
          key: String(index), detail: gap.detail, code: gap.code, scope: gap.scope, scopeLabel: scopeLabelFor(gap.scope),
          moduleKey: gap.module_key, recordId: gap.record_id,
          moduleTitle: report.modules.find((module) => module.module_key === gap.module_key)?.title,
          topicTitle: data?.coverage.find((entry) => entry.topic === gap.topic && entry.module_key === gap.module_key)?.title ?? gap.topic,
        }))} />
      </>}
    </Drawer>;
}
