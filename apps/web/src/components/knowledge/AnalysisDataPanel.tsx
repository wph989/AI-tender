"use client";

import { Alert, App, Button, Drawer, Input, Select, Space, Table, Tag, Tree } from "antd";
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
type ReviewTarget = Pick<BusinessRecord, "id" | "title" | "citations"
  | "verification" | "human_review" | "human_review_status"> & { kind: BusinessRecord["kind"] | "coverage" };
interface Props {
  report: AnalysisReport;
  onLocate: (citation: Citation) => void;
  snapshot: AnalysisDataSnapshot | null;
  open: boolean;
  onClose: () => void;
  onReviewChanged: () => void;
}

/** 预览固定一个标段；切换标段或报告时丢弃旧请求，避免旧依据覆盖新选择。 */
export function AnalysisDataPanel({ report, onLocate, snapshot, open, onClose, onReviewChanged }: Props) {
  const { message } = App.useApp();
  const [lotId, setLotId] = useState<number>();
  const [context, setContext] = useState<AnalysisContext | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [corrections, setCorrections] = useState<Record<string, string>>({});
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

  function citations(record: Pick<ReviewTarget, "citations">) {
    return <EvidenceReferences refs={record.citations} onLocate={(ref) => {
      previewAbort.current?.abort(); setBusy(false); onClose(); onLocate(ref);
    }} />;
  }

  async function review(record: ReviewTarget, decision: "confirmed" | "corrected" | "rejected") {
    if (!snapshot) return;
    const note = notes[record.id]?.trim() ?? "";
    const correctedText = corrections[record.id]?.trim() ?? "";
    if (decision !== "confirmed" && !note) {
      message.warning("请填写修正或驳回理由"); return;
    }
    if (decision === "corrected" && !correctedText) {
      message.warning("请填写修正后的内容"); return;
    }
    setReviewing(record.id);
    try {
      await knowledgeRequest(`/analysis/reports/${report.id}/reviews`, "POST", {
        snapshot_id: snapshot.snapshot_id, record_id: record.id,
        previous_review_id: record.human_review?.id ?? null, decision, note,
        corrected_text: decision === "corrected" ? correctedText : null,
      });
      // 裁定变化后旧预览已失效，重新加载快照以取得本次裁定版本。
      previewAbort.current?.abort(); setBusy(false); setContext(null); setPreviewError(null);
      message.success("人工复核已保存");
      onReviewChanged();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "复核失败，请重试");
    } finally { setReviewing(null); }
  }

  function reviewControls(record: ReviewTarget) {
    const status = record.human_review_status ?? "pending";
    const reviewReady = record.verification === "supported" && record.citations.length > 0;
    const label = ({ pending: "待人工复核", confirmed: "人工确认", corrected: "人工修正",
      rejected: "人工驳回", outdated: "资料已变更" } as const)[status];
    const editable = !report.stale && !snapshot?.stale && status !== "outdated";
    const canCorrect = record.kind === "fact" || record.kind === "requirement";
    return <div className="mt-2 flex flex-wrap items-center gap-2">
      <Tag color={record.verification === "supported" ? "blue" : "orange"}>
        {record.verification === "supported" ? "机器自查通过" : "机器自查未通过"}
      </Tag>
      <Tag color={status === "confirmed" || status === "corrected" ? "green"
        : status === "rejected" || status === "outdated" ? "red" : "gold"}>{label}</Tag>
      {record.human_review?.note && <span className="text-xs text-slate-500">复核说明：{record.human_review.note}</span>}
      {editable && <>
        {status !== "confirmed" && status !== "corrected" && <Button size="small" loading={reviewing === record.id}
          disabled={Boolean(reviewing) || !reviewReady} onClick={() => void review(record, "confirmed")}>确认</Button>}
        <Input aria-label={`${record.title} ${canCorrect ? "修正或驳回理由" : "驳回理由"}`} size="small"
          placeholder={canCorrect ? "修正/驳回理由（必填）" : "驳回理由（必填）"}
          value={notes[record.id] ?? ""} onChange={(event) => setNotes({ ...notes, [record.id]: event.target.value })}
          className="max-w-56" />
        {canCorrect && <>
          <Input aria-label={`${record.title} 修正内容`} size="small" placeholder="修正后的内容"
            value={corrections[record.id] ?? ""} onChange={(event) => setCorrections({ ...corrections, [record.id]: event.target.value })}
            className="max-w-64" />
          <Button size="small" disabled={Boolean(reviewing) || !reviewReady}
            loading={reviewing === record.id} onClick={() => void review(record, "corrected")}>保存修正</Button>
        </>}
        {status !== "rejected" && <Button size="small" danger disabled={Boolean(reviewing) || !reviewReady}
          loading={reviewing === record.id} onClick={() => void review(record, "rejected")}>驳回</Button>}
      </>}
      {!reviewReady && status === "pending" && <span className="text-xs text-slate-500">
        原文依据未齐，暂不能复核
      </span>}
    </div>;
  }

  function recordsTable(records: BusinessRecord[], preview = false) {
    return <Table<BusinessRecord> size="small" rowKey="id" dataSource={records}
      pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
      scroll={{ x: 550 }} columns={[
        { title: "事项", dataIndex: "title", width: 135 },
        { title: "依据内容", render: (_, row) => <div className="whitespace-pre-wrap break-words">
          {!preview && row.human_review?.decision === "corrected" ? <>
            <p className="mb-1"><strong>人工修正：</strong>{row.human_review.corrected_text}</p>
            <p className="mb-1 text-slate-600"><strong>机器原文：</strong>{row.text}</p>
          </> : row.text}
          {citations(row)}{!preview && reviewControls(row)}
          {Boolean(row.superseded_in?.length) && <Tag>部分范围已有修订</Tag>}
          {Boolean(row.conflicts_in?.length) && <Tag color="gold">存在待核对冲突</Tag>}</div> },
        { title: "适用范围", width: 115, render: (_, row) => scopeLabelFor(row.scope) },
      ]} />;
  }

  function tree(nodes: BusinessRecord[], preview = false): DataNode[] {
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
          <p className="whitespace-pre-wrap">{node.text}</p>{citations(node)}{!preview && reviewControls(node)}</div>,
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
  const coverage = data?.coverage.flatMap((item) => item.status === "not_applicable"
    && item.review_id && item.citations?.length
    ? [{ ...item, id: item.review_id, kind: "coverage" as const, citations: item.citations,
      verification: item.verification ?? "unsupported" }] : []) ?? [];
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
      {data && <>
        <Alert className="mb-3" type={snapshot?.stale || report.stale ? "error" : "info"}
          title={snapshot?.stale || report.stale ? "分析资料已变更，当前结果只可查看" : "机器分析结果须逐项人工复核后才进入编制依据"} />
        {([
          ["标段", data.lots], ["项目事实", data.facts], ["招标要求", data.requirements],
          ["关系", data.relations],
        ] as [string, BusinessRecord[]][]).map(([title, records]) => records.length > 0 && <details key={title} className="mb-3">
          <summary className="cursor-pointer py-2 font-medium">{title}（{records.length}）</summary>
          {recordsTable(records)}
        </details>)}
        {data.format_nodes.length > 0 && <details className="mb-3">
          <summary className="cursor-pointer py-2 font-medium">格式目录（{data.format_nodes.length}）</summary>
          <Tree className="my-3" showLine defaultExpandAll treeData={tree(data.format_nodes)} />
        </details>}
        {coverage.length > 0 && <details className="mb-3">
          <summary className="cursor-pointer py-2 font-medium">不适用结论（{coverage.length}）</summary>
          <Table<(typeof coverage)[number]> size="small" rowKey="id" dataSource={coverage}
            pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
            scroll={{ x: 550 }} columns={[
              { title: "专题事项", width: 135, render: (_, row) => <>
                {row.title}
                <div className="text-xs text-slate-600">{report.modules.find((m) => m.module_key === row.module_key)?.title}</div>
              </> },
              { title: "不适用依据", render: (_, row) => <div className="whitespace-pre-wrap break-words">
                {row.detail}{citations(row)}{reviewControls(row)}</div> },
              { title: "适用范围", width: 115, render: (_, row) => scopeLabelFor(row.scope) },
            ]} />
        </details>}
      </>}
      {previewError && <Alert className="mb-3" type="error" title={previewError} />}
      {context && <>
        <Alert className="mb-3" type={context.readiness === "usable" ? "success" : "warning"}
        title={readinessLabels[context.readiness]} description={`共 ${context.total_requirements} 项适用要求。${context.readiness === "usable" ? "" : "请完成逐项人工复核后再将依据用于编制。"}`} />
        {context.facts.length > 0 && <><h3 className="my-3 font-medium">项目信息</h3>{recordsTable(context.facts, true)}</>}
        <h3 className="my-3 font-medium">适用要求</h3>
        <div className="analysis-context-requirements">{recordsTable(context.requirements, true)}</div>
        {context.next_offset !== null && <Button className="my-3" loading={busy} onClick={() => void preview(true)}>加载更多要求</Button>}
        {context.format_nodes.length > 0 && <Tree className="my-3" showLine defaultExpandAll treeData={tree(context.format_nodes, true)} />}
        {context.unresolved.length > 0 && <><h3 className="my-3 font-medium">适用标段或条款版本待核对</h3>{recordsTable(context.unresolved, true)}</>}
        <ResearchGaps gaps={context.gaps.map((gap, index) => ({
          key: String(index), detail: gap.detail, code: gap.code, scope: gap.scope, scopeLabel: scopeLabelFor(gap.scope),
          moduleKey: gap.module_key, recordId: gap.record_id,
          moduleTitle: report.modules.find((module) => module.module_key === gap.module_key)?.title,
          topicTitle: data?.coverage.find((entry) => entry.topic === gap.topic && entry.module_key === gap.module_key)?.title ?? gap.topic,
        }))} />
      </>}
    </Drawer>;
}
