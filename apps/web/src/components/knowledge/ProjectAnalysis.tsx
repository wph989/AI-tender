"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppRail } from "@/components/AppRail";
import { Icon } from "@/components/Icon";
import { BUTTON_CLASS, PRIMARY_BUTTON_CLASS, SELECT_CLASS } from "@/components/ui";
import { knowledgeRequest, resolveCitation } from "@/lib/api/knowledge";
import { loadProject } from "@/lib/api/client";
import type { AnalysisReport, AnalysisStatus, Citation, KnowledgeCollection } from "@/types/knowledge";
import { STATE_LABELS } from "@/types/knowledge";
import { CitationViewer } from "./CitationViewer";
import { ReportItems } from "./ReportItems";
import { QuestionPanel } from "./QuestionPanel";

export function ProjectAnalysis({ projectId }: { projectId: number }) {
  const [name, setName] = useState("项目分析");
  const [state, setState] = useState<AnalysisStatus | null>(null);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [category, setCategory] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [lots, setLots] = useState<AnalysisStatus["lots"]>([]);
  const [allowPartial, setAllowPartial] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"report" | "ask">("report");
  const [collections, setCollections] = useState<KnowledgeCollection[]>([]);
  const [linked, setLinked] = useState<number[]>([]);
  const [selected, setSelected] = useState<Citation | null>(null);
  const [answerRefs, setAnswerRefs] = useState<Citation[]>([]);
  const [mobileDocument, setMobileDocument] = useState(false);
  const [activeItem, setActiveItem] = useState<string>();
  const chosenReport = useRef<number | null>(null);
  const initialized = useRef(false);
  const locateAbort = useRef<AbortController | null>(null);
  const loadSequence = useRef(0);

  const reload = useCallback(async () => {
    const sequence = ++loadSequence.current;
    const next = await knowledgeRequest<AnalysisStatus>("/projects/" + projectId + "/analysis");
    if (sequence !== loadSequence.current) return;
    setState(next);
    if (!initialized.current) {
      setCategory(next.analysis_category ?? ""); setTopics(next.analysis_topics); setLots(next.lots);
      initialized.current = true;
    }
    const id = chosenReport.current ?? next.reports[0]?.id;
    if (id) {
      const loaded = await knowledgeRequest<AnalysisReport>("/analysis/reports/" + id);
      if (sequence === loadSequence.current) setReport(loaded);
    }
  }, [projectId]);

  useEffect(() => {
    void reload().catch((e: Error) => setError(e.message));
    void loadProject(projectId).then((p) => setName(p.name)).catch((e: Error) => setError(e.message));
    void Promise.all([
      knowledgeRequest<{ items: KnowledgeCollection[] }>("/knowledge/collections"),
      knowledgeRequest<{ linked_collection_ids: number[] }>("/projects/" + projectId + "/knowledge"),
    ]).then(([all, association]) => { setCollections(all.items.filter((c) => !c.is_project)); setLinked(association.linked_collection_ids); }).catch((e: Error) => setError(e.message));
    return () => { ++loadSequence.current; locateAbort.current?.abort(); };
  }, [projectId, reload]);
  const running = state?.reports.some((r) => ["waiting", "pending", "running"].includes(r.status)) ?? false;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => { void reload().catch((e: Error) => setError(e.message)); }, 3000);
    return () => clearInterval(timer);
  }, [running, reload]);

  const refs = useMemo(() => [...(report?.modules.flatMap((m) => m.items.flatMap((i) => i.citations)) ?? []), ...answerRefs], [report, answerRefs]);
  const locate = useCallback(async (ref: Citation) => {
    locateAbort.current?.abort();
    const controller = new AbortController(); locateAbort.current = controller;
    try {
      const resolved = await resolveCitation(ref, controller.signal);
      if (!controller.signal.aborted) { setSelected(resolved); setMobileDocument(true); }
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "原文无法打开"); }
  }, []);
  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await action(); await reload(); } catch (e) { setError(e instanceof Error ? e.message : "操作失败"); }
    finally { setBusy(false); }
  };

  return <div className="workspace analysis-workspace">
    <AppRail />
    <header className="workspace-heading">
      <Link href="/projects" className="back-button" aria-label="返回项目空间"><Icon name="back" size={16} /></Link>
      <div className="min-w-0"><p className="text-xs text-slate-400">项目空间 / 综合分析</p><h1>{name}</h1></div>
      <div className="ml-auto flex shrink-0 gap-2"><Link href={"/projects/" + projectId + "?view=fields"} className={BUTTON_CLASS}>字段复核</Link><Link href={"/projects/" + projectId + "/files"} className={BUTTON_CLASS}>文件管理</Link></div>
    </header>
    <main id="main-content" className="analysis-main" tabIndex={-1}>
      {error && <div role="alert" className="notice mb-3">{error}<button className="ml-auto" onClick={() => setError(null)} aria-label="关闭提示">×</button></div>}
      <div className="analysis-command-bar">
        <div className="flex gap-1" role="group" aria-label="分析视图"><button aria-pressed={tab === "report"} onClick={() => setTab("report")}>分析报告</button><button aria-pressed={tab === "ask"} onClick={() => setTab("ask")}>项目问答</button></div>
        <span className="analysis-file-count">全部 {state?.sources.length ?? 0} 份材料共同分析</span>
        <button className={PRIMARY_BUTTON_CLASS} disabled={busy || running || !category} onClick={() => void perform(async () => {
          await knowledgeRequest("/projects/" + projectId + "/analysis/settings", "PUT", { category, topics, lots: lots.map(({ id, category, topics }) => ({ id, category, topics })) });
          const result = await knowledgeRequest<{ id: number }>("/projects/" + projectId + "/analysis", "POST", { allow_partial: allowPartial });
          chosenReport.current = result.id; setTab("report");
        })}>{running ? "分析任务进行中" : report ? "更新分析" : "开始分析"}</button>
      </div>
      <details className="analysis-options" open={!report || undefined}>
        <summary>分析范围与设置 <span>{state?.categories[category] ?? "请先选择项目类别"}</span></summary>
        <div className="analysis-options-body">
          <fieldset><legend>项目类别</legend><div className="flex flex-wrap gap-4">{Object.entries(state?.categories ?? {}).map(([key, label]) => <label key={key}><input type="radio" name="category" checked={category === key} onChange={() => setCategory(key)} /> {label}</label>)}</div></fieldset>
          <fieldset><legend>附加专题</legend><div className="flex flex-wrap gap-4">{Object.entries(state?.topics ?? {}).map(([key, label]) => <label key={key}><input type="checkbox" checked={topics.includes(key)} onChange={(e) => setTopics(e.target.checked ? [...topics, key] : topics.filter((t) => t !== key))} /> {label}</label>)}</div></fieldset>
          {lots.length > 0 && <fieldset><legend>标段类别与专题</legend>{lots.map((lot, index) => <div className="mb-3 flex flex-wrap items-center gap-3" key={lot.id}><span>{lot.name}</span><select aria-label={lot.name + "类别"} className={SELECT_CLASS} value={lot.category ?? ""} onChange={(e) => setLots(lots.map((v, i) => i === index ? { ...v, category: e.target.value || null } : v))}><option value="">继承项目类别</option>{Object.entries(state?.categories ?? {}).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
            <label><input type="checkbox" checked={lot.topics === null} onChange={(e) => setLots(lots.map((v, i) => i === index ? { ...v, topics: e.target.checked ? null : [] } : v))} /> 继承项目专题</label>
            {lot.topics !== null && Object.entries(state?.topics ?? {}).map(([key, label]) => <label key={key}><input type="checkbox" checked={lot.topics?.includes(key) ?? false} onChange={(e) => setLots(lots.map((v, i) => i === index ? { ...v, topics: e.target.checked ? [...(v.topics ?? []), key] : v.topics?.filter((t) => t !== key) ?? [] } : v))} /> {label}</label>)}
          </div>)}</fieldset>}
          <label className="block"><input type="checkbox" checked={allowPartial} onChange={(e) => setAllowPartial(e.target.checked)} /> 文件未全部就绪时，先分析可用材料并标明缺失</label>
          <div className="source-coverage">{state?.sources.map((source) => <span key={source.source_id} data-state={source.state} title={source.error_message ?? source.file_name}><span className="truncate">{source.file_name}</span><b>{STATE_LABELS[source.state] ?? source.state}</b></span>)}</div>
          {collections.length > 0 && <fieldset><legend>问答可参考的知识库</legend><p className="mb-2 text-xs text-slate-500">综合报告以本项目材料为依据；关联资料用于问答中的补充参考。</p><div className="flex flex-wrap gap-4">{collections.map((collection) => <label key={collection.id}><input type="checkbox" disabled={busy} checked={linked.includes(collection.id)} onChange={(e) => {
            const next = e.target.checked ? [...linked, collection.id] : linked.filter((i) => i !== collection.id);
            void perform(async () => { await knowledgeRequest("/projects/" + projectId + "/knowledge/collections", "PUT", { collection_ids: next }); setLinked(next); });
          }} /> {collection.name}</label>)}</div></fieldset>}
        </div>
      </details>
      {report?.stale && <p className="notice my-2">项目材料或分析设置已变化。这份报告保留原版本依据，请更新分析。</p>}
      <div className="analysis-mobile-switch"><button aria-pressed={!mobileDocument} onClick={() => setMobileDocument(false)}>分析内容</button><button aria-pressed={mobileDocument} disabled={!selected} onClick={() => setMobileDocument(true)}>引用原文</button></div>
      <div className="analysis-split" data-document={mobileDocument}>
        <section className="analysis-content">
          {tab === "ask" ? <QuestionPanel endpoint={"/projects/" + projectId + "/knowledge/ask"} collectionIds={linked} onLocate={(ref) => void locate(ref)} onCitations={setAnswerRefs} />
          : !report ? <div className="empty-state"><span className="empty-icon"><Icon name="scan" size={28} /></span><h2>把分散的条款，汇成一份有据可查的报告</h2><p>选择类别后开始分析。项目内的招标文件、澄清、补遗和附件会一并核对。</p>{!state && <p role="status">正在加载资料…</p>}</div>
          : <>
            <div className="report-heading"><div><p className="text-xs text-slate-400">项目综合报告</p><h2>{STATE_LABELS[report.status] ?? report.status}</h2></div>
              <select aria-label="选择报告版本" className={SELECT_CLASS} value={report.id} onChange={(e) => { chosenReport.current = Number(e.target.value); void reload().catch((caught: Error) => setError(caught.message)); }}>
                {state?.reports.map((r) => <option key={r.id} value={r.id}>报告 #{r.id} · {STATE_LABELS[r.status] ?? r.status}</option>)}
              </select>
            </div>
            {report.coverage.total_blocks ? <p className="mb-3 text-sm text-slate-500">全文阅读覆盖：{report.coverage.scanned_blocks} / {report.coverage.total_blocks} 个原文块</p> : null}
            {report.coverage.partial && <p className="notice mb-3">本报告覆盖不完整，请在范围设置中核对缺失或部分解析的文件。</p>}
            {report.status === "waiting" && <p className="notice mb-3">正在等待本次全部文件可用。请到文件管理查看失败原因；需要先分析可用材料时，可取消本次任务后勾选部分分析。</p>}
            {report.error_message && <p role="alert" className="notice mb-3">{report.error_message}</p>}
            {["waiting", "pending", "running"].includes(report.status) && <button className={BUTTON_CLASS + " mb-3"} disabled={busy} onClick={() => void perform(() => knowledgeRequest("/analysis/reports/" + report.id + "/cancel", "POST", {}))}>取消任务</button>}
            {report.status === "failed" && <button className={BUTTON_CLASS + " mb-3"} disabled={busy || running} onClick={() => void perform(() => knowledgeRequest("/analysis/reports/" + report.id + "/retry", "POST", {}))}>重试分析</button>}
            {report.modules.map((module) => <section key={module.id} className="report-module"><div className="report-module-heading"><h3>{module.title}</h3><span>{STATE_LABELS[module.status] ?? module.status}</span></div>
              {module.status === "failed" ? <div className="notice"><span>{module.error_message}</span><button className={BUTTON_CLASS} disabled={busy || running} onClick={() => void perform(() => knowledgeRequest("/analysis/reports/" + report.id + "/retry", "POST", { module_keys: [module.module_key] }))}>补跑本模块</button></div>
                : module.items.length ? <ReportItems items={module.items} activeId={activeItem} onLocate={(ref) => void locate(ref)} /> : <p className="py-3 text-sm text-slate-500">{module.status === "completed" ? "当前材料中未找到该主题的明确要求。" : "正在阅读与核对原文…"}</p>}
            </section>)}
          </>}
        </section>
        <aside className="analysis-document">{selected ? <CitationViewer key={selected.version_id + ":" + selected.parse_run_id} selected={selected} citations={refs.includes(selected) ? refs : [...refs, selected]} onReverse={(ref) => {
          const item = report?.modules.flatMap((m) => m.items).find((i) => i.citations.some((r) => r.source_id === ref.source_id && r.element_id === ref.element_id));
          if (item) { setTab("report"); setActiveItem(item.id); setMobileDocument(false); setTimeout(() => document.getElementById("report-item-" + item.id)?.scrollIntoView({ block: "center" }), 0); }
        }} /> : <div className="empty-state"><Icon name="book" size={32} /><h3>原文就在结论旁边</h3><p>点击报告或回答中的引用，查看对应文件、页码和高亮位置。</p></div>}</aside>
      </div>
    </main>
  </div>;
}
