"use client";

import { Alert, Button, Input, Select } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useAnalysisSnapshot } from "@/hooks/useAnalysisSnapshot";
import { filterResults, resultCounts, unpairedFields } from "@/lib/analysis/presentation";
import { groupGaps, type DisplayGap } from "@/lib/analysis/gaps";
import { scopeLabel } from "@/lib/analysis/scope";
import { formatDateTime } from "@/lib/format";
import { isActive, STATE_LABELS, type AnalysisReport, type Citation } from "@/types/knowledge";
import { AnalysisDataPanel } from "./AnalysisDataPanel";
import { AnalysisFailureNotice } from "./AnalysisFailureNotice";
import { ModuleMarkdown } from "./ModuleMarkdown";
import { ResearchGaps } from "./ResearchGaps";

interface Props {
  report: AnalysisReport;
  reports: Pick<AnalysisReport, "id" | "status" | "created_at">[];
  activeModuleId: number | null;
  activeItem?: string;
  locationRevision: number;
  busy: boolean;
  running: boolean;
  onChooseReport: (id: number) => void;
  onChooseModule: (id: number | null) => void;
  onActiveItem: (id?: string) => void;
  onLocate: (ref: Citation, itemId?: string) => void;
  onRefresh: () => void;
  onAction: (action: "retry" | "cancel", keys?: string[]) => void;
}

/** 专题正文是唯一主阅读入口，快照只补充范围、关联及待核对信息。 */
export function AnalysisResults({ report, reports, activeModuleId, activeItem, locationRevision, busy, running,
  onChooseReport, onChooseModule, onActiveItem, onLocate, onRefresh, onAction }: Props) {
  const { snapshot, error, loading, reload, terminal } = useAnalysisSnapshot(report);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("");
  const [group, setGroup] = useState("");
  const [attention, setAttention] = useState(false);
  const [view, setView] = useState<"results" | "gaps">("results");
  const [previewOpen, setPreviewOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const positions = useRef(new Map<number, number>());
  const data = snapshot?.data;
  const modules = useMemo(() => {
    const byId = new Map([...(data?.facts ?? []), ...(data?.requirements ?? []),
      ...(data?.format_nodes ?? []), ...(data?.relations ?? []), ...(data?.lots ?? [])]
      .map((record) => [record.id, record]));
    return report.modules.map((module) => ({ ...module, items: module.items.map((item) => ({
      ...item, record: byId.get(item.id) ?? item.record,
    })) }));
  }, [report.modules, data]);
  const allItems = useMemo(() => modules.flatMap((module) => module.items), [modules]);
  const counts = useMemo(() => resultCounts(modules), [modules]);
  // 0 是明确的全部专题；null 只负责初次打开时选有成果的专题。
  const currentId = activeModuleId === 0 ? 0 : modules.find((module) => module.id === activeModuleId)?.id
    ?? modules.find((module) => module.items.length)?.id ?? modules[0]?.id ?? 0;
  const current = modules.find((module) => module.id === currentId);
  const selectedModules = current ? [current] : modules;
  const canResume = ["failed", "partial", "canceled"].includes(report.status)
    && (!modules.length || modules.some((module) => module.status !== "completed"));
  const gaps = useMemo<DisplayGap[]>(() => {
    const existing: DisplayGap[] = data ? data.gaps.map((gap, index) => {
      // 记录级缺口未必重复写 module_key，仍应归到对应事项，避免混入每一个专题。
      const module = modules.find((entry) => entry.module_key === gap.module_key
        || entry.items.some((item) => item.id === gap.record_id));
      return {
        key: gap.key ?? `data-${index}`, detail: gap.detail, code: gap.code, scope: gap.scope,
        moduleKey: module?.module_key ?? gap.module_key, recordId: gap.record_id,
        moduleTitle: module?.title ?? "报告整体",
        topicTitle: data.coverage.find((entry) => entry.module_key === module?.module_key && entry.topic === gap.topic)?.title
          ?? module?.items.find((item) => item.id === gap.record_id)?.field ?? gap.topic,
        scopeLabel: scopeLabel(gap.scope, (id) => data.lots.find((lot) => lot.lot_id === id)?.title),
      };
    }) : modules.flatMap((module) => (module.research_gaps ?? []).map((gap) => ({
      ...gap, key: `${module.id}:${gap.key}`, moduleKey: module.module_key, moduleTitle: module.title,
      code: gap.key.startsWith("reference:") ? "unresolved_reference" : "search_exhausted",
    })));
    for (const module of modules) for (const item of module.items) if (unpairedFields(item)) {
      existing.push({ key: `pair:${item.id}`, code: "unpaired_fields", recordId: item.id,
        moduleKey: module.module_key, moduleTitle: module.title, topicTitle: item.field,
        scope: item.record?.scope, scopeLabel: item.record ? scopeLabel(item.record.scope) : undefined,
        detail: "字段与内容数量不一致，缺失项已在表格中标出；请核对原文后重新解析本模块。" });
    }
    return existing;
  }, [data, modules]);
  const visibleGaps = current ? gaps.filter((gap) => gap.moduleKey === current.module_key || !gap.moduleKey) : gaps;
  const visible = selectedModules.map((module) => ({ ...module,
    items: filterResults(module.items, { query, scope, group, attention, gaps: data?.gaps }),
  }));
  const matchedCount = visible.reduce((total, module) => total + module.items.filter((item) => !item.contextOnly).length, 0);
  const scopes = new Map<string, string>();
  for (const item of allItems) {
    const value = item.record?.scope;
    if (value?.kind !== "lots") continue;
    if ("lot_ids" in value && value.lot_ids.length) value.lot_ids.forEach((id, index) =>
      scopes.set(`id:${id}`, data?.lots.find((lot) => lot.lot_id === id)?.title ?? value.lot_refs[index] ?? `标段 ${id}`));
    else value.lot_refs.forEach((ref) => scopes.set(`ref:${ref}`, ref));
  }
  const categories = [...new Set(selectedModules.flatMap((module) => module.items.map((item) => item.group)).filter(Boolean))];
  const resetFilters = () => { setQuery(""); setScope(""); setGroup(""); setAttention(false); };
  function chooseModule(id: number) {
    const scroller = root.current?.closest(".analysis-content");
    positions.current.set(currentId, scroller?.scrollTop ?? 0);
    onActiveItem(undefined); setGroup(""); onChooseModule(id);
    requestAnimationFrame(() => { if (scroller) scroller.scrollTop = positions.current.get(id) ?? 0; });
  }
  function reveal(id: string) {
    const module = modules.find((entry) => entry.items.some((item) => item.id === id));
    if (!module) return;
    resetFilters(); setView("results"); onChooseModule(module.id); onActiveItem(id);
  }
  useEffect(() => {
    // 原文或缺口跳转也会切换模块，让窄屏标签同步滚到当前模块。
    root.current?.querySelector(`[data-module-id="${currentId}"]`)
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [currentId]);
  useEffect(() => {
    if (!activeItem) return;
    setQuery(""); setScope(""); setGroup(""); setAttention(false); setView("results");
    // 子树展开发生在同一帧，下一帧再定位，避免滚到隐藏节点。
    const timer = setTimeout(() => document.getElementById("report-item-" + activeItem)
      ?.scrollIntoView({ block: "center" }), 50);
    return () => clearTimeout(timer);
  }, [activeItem, locationRevision]);
  function navigateGap(gap: DisplayGap) {
    if (gap.recordId && allItems.some((item) => item.id === gap.recordId)) return reveal(gap.recordId);
    const module = modules.find((entry) => entry.module_key === gap.moduleKey);
    if (module) { resetFilters(); chooseModule(module.id); setView("results"); }
  }
  return <div ref={root} className="analysis-results">
    <div className="results-overview">
      <div className="results-report-bar">
        <strong>解析结果 <span className="report-status">{STATE_LABELS[report.status] ?? report.status}</span></strong>
        <Select<string> aria-label="选择报告版本" value={String(report.id)}
          onChange={(value) => onChooseReport(Number(value))} options={reports.map((entry) => ({
            value: String(entry.id), label: `报告 #${entry.id} · ${STATE_LABELS[entry.status] ?? entry.status}`,
          }))} />
      </div>
      <p className="results-counts" aria-label="结果统计">
        报告记录：信息 {counts.facts} · 要求 {counts.requirements} · 材料节点 {counts.materials} · 关联 {counts.relations}
        {counts.other > 0 && ` · 历史条目 ${counts.other}`}
        <span>专题完成 {modules.filter((module) => module.status === "completed").length}/{modules.length}</span>
      </p>
      <div className="report-actions" role="group" aria-label="报告操作">
        <Button onClick={onRefresh}>刷新结果</Button>
        {!report.runtime_retired && <Button disabled={busy || running || !current || isActive(current?.status)}
          title={current ? `重新解析：${current.title}` : "请先选择一个专题"}
          onClick={() => { if (current) onAction("retry", [current.module_key]); }}>重新解析本模块</Button>}
        {isActive(report.status) && <Button disabled={busy || report.canceling} onClick={() => onAction("cancel")}>取消任务</Button>}
        {!report.runtime_retired && <Button disabled={busy || running || !canResume}
          onClick={() => onAction("retry")}>补跑未完成模块</Button>}
        {!report.runtime_retired && modules.length > 0 && <Button disabled={busy || running || !terminal}
          onClick={() => onAction("retry", modules.map((module) => module.module_key))}>全部重新解析</Button>}
        {report.runtime_retired && <p>旧流程报告仅供查看，需要最新结果请生成新报告。</p>}
      </div>
    </div>
    <div className="results-sticky">
      <div className="module-tabs results-module-tabs" role="tablist" aria-label="解析专题"
        onKeyDown={(event) => {
          // 标签支持方向键与首尾跳转，窄屏也可直接定位当前标签。
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
          const index = buttons.indexOf(event.target as HTMLButtonElement);
          if (index < 0) return;
          const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
            : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
          event.preventDefault();
          const button = buttons[next]!;
          chooseModule(Number(button.dataset.moduleId)); button.focus();
          button.scrollIntoView({ block: "nearest", inline: "nearest" });
        }}>
        {[{ id: 0, title: "全部专题", status: "", count: allItems.length }, ...modules.map((module) => ({
          id: module.id, title: module.title, status: module.status, count: module.items.length,
        }))].map((module) => <button key={module.id} type="button" role="tab" data-module-id={module.id}
          id={`module-tab-${report.id}-${module.id}`} aria-controls={`module-panel-${report.id}`}
          aria-selected={currentId === module.id} tabIndex={currentId === module.id ? 0 : -1}
          data-status={module.status} onClick={() => chooseModule(module.id)}>
          <span>{module.title}</span><small className="module-tab-status">
            {!module.status || module.status === "completed" ? `${module.count} 条` : STATE_LABELS[module.status] ?? module.status}
          </small>
        </button>)}
      </div>
      <div className="results-mode" role="tablist" aria-label="结果阅读方式">
        <button type="button" role="tab" aria-selected={view === "results"} onClick={() => setView("results")}>解析正文</button>
        <button type="button" role="tab" aria-selected={view === "gaps"} onClick={() => setView("gaps")}>待核对 · {groupGaps(visibleGaps).length} 组</button>
        {report.data_schema_version && !report.runtime_retired && <Button size="small"
          title={data?.readiness === "unavailable" ? "依据不足，请先查看待核对事项" : undefined}
          disabled={!snapshot || report.stale || snapshot.stale || data?.readiness === "unavailable"}
          onClick={() => setPreviewOpen(true)}>按标段查看要求</Button>}
      </div>
      <div className="results-filters">
        {view === "results" && <><label>适用范围<select aria-label="筛选适用范围" value={scope} onChange={(event) => {
          onActiveItem(undefined); setScope(event.target.value);
        }}><option value="">全部范围</option><option value="common">仅公共要求</option><option value="unknown">范围待确认</option>
          {[...scopes].map(([value, title]) => <option key={value} value={value}>{title}（含公共要求）</option>)}
        </select></label>
          <Input.Search allowClear aria-label="搜索解析结果" placeholder="搜索事项、内容" value={query}
            onChange={(event) => { onActiveItem(undefined); setQuery(event.target.value); }} />
        </>}
      </div>
    </div>
    {report.canceling && <Alert type="info" title="正在停止分析，结束后可继续未完成的专题。" />}
    {report.status === "waiting" && <p className="notice">正在等待本次全部文件可用，可到文件管理查看处理进度。</p>}
    {report.error_message && <AnalysisFailureNotice message={report.error_message} canceled={report.status === "canceled"} />}
    {report.stale && <Alert type="warning" title="资料已变化，当前报告为历史结果，请生成新报告。" />}
    {report.coverage.partial && <p className="notice">部分文件尚未完整读取，当前结果保留可用依据。</p>}
    {error && <details className="snapshot-notice"><summary>标段汇总暂不可用，专题正文仍可查看</summary>
      <p>{error}</p><Button size="small" onClick={reload}>重试加载汇总</Button></details>}
    {loading && <p className="snapshot-notice" role="status">正在核对跨专题范围与关联…</p>}
    <div id={`module-panel-${report.id}`} role="tabpanel" aria-labelledby={`module-tab-${report.id}-${currentId}`}>
    {view === "gaps" ? <>
      {!!data?.coverage.length && <details className="coverage-details"><summary>查看专题检查进度</summary>
        <ul>{data.coverage.filter((entry) => !current || entry.module_key === current.module_key).map((entry, index) => <li key={index}>
          <strong>{modules.find((module) => module.module_key === entry.module_key)?.title} · {entry.title}</strong>
          <p>{({ extracted: "已汇总", searched_not_found: "本次检索未找到", pending: "尚未核对完整",
            not_applicable: "已确认不适用", unchecked: "未检查" } as Record<string, string>)[entry.status] ?? entry.status}
            {" · "}{scopeLabel(entry.scope)}</p><p>{entry.detail}</p>
        </li>)}</ul>
      </details>}
      <ResearchGaps gaps={visibleGaps} expanded onNavigate={navigateGap} />
      {!visibleGaps.length && <p className="result-empty">当前专题没有已登记的待核对事项；条目数量不代表原文已完整覆盖。</p>}
    </> : <>
      <div className="results-subfilters">
        <select aria-label="筛选结果分类" value={group} onChange={(event) => { onActiveItem(undefined); setGroup(event.target.value); }}>
          <option value="">全部分类</option>{categories.map((name) => <option key={name}>{name}</option>)}
        </select>
        <label><input type="checkbox" checked={attention} onChange={(event) => { onActiveItem(undefined); setAttention(event.target.checked); }} /> 仅待核对条目</label>
        <span>{matchedCount} 条匹配</span>
        {(query || scope || group || attention) && <button type="button" onClick={resetFilters}>清除筛选</button>}
      </div>
      {visible.map((module) => <section key={module.id} className="report-module" aria-label={module.title}>
        <div className="report-module-heading"><h3>{module.title}</h3>
          {!!gaps.filter((gap) => gap.moduleKey === module.module_key).length && <button type="button" className="module-gap-link"
            onClick={() => { onChooseModule(module.id); setView("gaps"); }}>查看本专题待核对事项</button>}
        </div>
        <details className="module-operations"><summary>{module.status === "completed" ? "分析记录" : `${STATE_LABELS[module.status] ?? module.status} · 查看原因与运行记录`}</summary>
          {["failed", "canceled"].includes(module.status) && <AnalysisFailureNotice message={module.error_message}
            canceled={module.status === "canceled"} />}
          {!!module.runs?.length && <ol className="analysis-runs" aria-label="历次分析记录">
            {module.runs.map((run) => <li key={run.id} className="run-detail" aria-label={`第 ${run.attempt} 次分析`}>
              <div className="run-summary"><strong>第 {run.attempt} 次 · {STATE_LABELS[run.status] ?? run.status}</strong>
                <span>模型请求 {run.model_calls}/{run.limits.max_model_calls} · 工具调用 {run.tool_calls}/{run.limits.max_tool_calls}</span>
              </div>
              <dl className="run-times">
                <div><dt>开始时间</dt><dd><time dateTime={run.started_at ?? undefined}>{formatDateTime(run.started_at)}</time></dd></div>
                <div><dt>结束时间</dt><dd>{run.finished_at
                  ? <time dateTime={run.finished_at}>{formatDateTime(run.finished_at)}</time>
                  : isActive(run.status) ? "尚未结束" : "未记录"}</dd></div>
              </dl>
              {/* 每次尝试独立保留原因，后续成功不能覆盖此前失败或取消的信息。 */}
              {(run.error_message || ["failed", "canceled"].includes(run.status)) && <p className="run-error" data-status={run.status}>
                <strong>{run.status === "canceled" ? "停止原因" : run.status === "failed" ? "失败原因" : "运行说明"}：</strong>
                {run.error_message || "未记录"}
              </p>}
            </li>)}
          </ol>}
          {module.research_summary && <details className="research-process"><summary>查看分析过程</summary><p>{module.research_summary}</p></details>}
        </details>
        {module.records_loading ? <p role="status">正在加载专题结果…</p> : module.records_error ? <Alert type="error" title="专题结果读取失败"
          description={module.records_error} action={<Button onClick={onRefresh}>重新加载</Button>} /> : module.items.length ? <ModuleMarkdown
          items={module.items} relatedItems={allItems} resolvedRelations={data?.relations}
          filtered={Boolean(query.trim() || scope || group || attention)} activeId={activeItem}
          locationRevision={locationRevision} onLocate={onLocate} onRevealItem={reveal} />
          : <p className="result-empty">{query || scope || group || attention ? "当前筛选没有匹配结果。" : module.status === "completed"
            ? "本次未形成已核实结果，请结合待核对事项了解检索范围。" : isActive(module.status)
              ? "正在检索与核对原文，已有可靠结果会持续保存。" : "本次还没有可用的分析结果，可展开上方记录查看原因。"}</p>}
      </section>)}
      {!modules.length && <p className="result-empty">{isActive(report.status) ? "专题尚未生成，请等待任务就绪。"
        : ["failed", "partial", "canceled"].includes(report.status) && !report.runtime_retired
          ? "专题尚未生成，可点击上方补跑未完成模块。" : "这份报告没有保存专题结果。"}</p>}
    </>}
    </div>
    <AnalysisDataPanel report={report} snapshot={snapshot} open={previewOpen} onClose={() => setPreviewOpen(false)} onLocate={onLocate} />
  </div>;
}
