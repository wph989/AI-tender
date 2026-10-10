"use client";
import { useFeedback } from "@/hooks/useFeedback";
import { Alert, Button, Segmented, Select, Tabs } from "antd";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppRail } from "@/components/AppRail";
import { Icon } from "@/components/Icon";
import { BUTTON_CLASS } from "@/components/ui";
import { knowledgeRequest, resolveCitation } from "@/lib/api/knowledge";
import { loadProject } from "@/lib/api/client";
import type {
  AnalysisReport,
  AnalysisStatus,
  Citation,
  KnowledgeCollection,
} from "@/types/knowledge";
import { STATE_LABELS } from "@/types/knowledge";
import { CitationViewer } from "./CitationViewer";
import { ModuleMarkdown } from "./ModuleMarkdown";
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
  useFeedback(error);
  const [tab, setTab] = useState<"report" | "ask">("report");
  // 模块标签页：用户要求按解析模块切换结果，默认停留在第一个已完成模块；无完成时回落到全部模块。
  const [activeModuleId, setActiveModuleId] = useState<number | null>(null);
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
    const next = await knowledgeRequest<AnalysisStatus>(
      "/projects/" + projectId + "/analysis",
    );
    if (sequence !== loadSequence.current) return;
    setState(next);
    if (!initialized.current) {
      setCategory(next.analysis_category ?? "");
      setTopics(next.analysis_topics);
      setLots(next.lots);
      initialized.current = true;
    }
    const id = chosenReport.current ?? next.reports[0]?.id;
    if (id) {
      const loaded = await knowledgeRequest<AnalysisReport>(
        "/analysis/reports/" + id,
      );
      if (sequence === loadSequence.current) setReport(loaded);
    }
  }, [projectId]);

  useEffect(() => {
    void reload().catch((e: Error) => setError(e.message));
    void loadProject(projectId)
      .then((p) => setName(p.name))
      .catch((e: Error) => setError(e.message));
    void Promise.all([
      knowledgeRequest<{ items: KnowledgeCollection[] }>(
        "/knowledge/collections",
      ),
      knowledgeRequest<{ linked_collection_ids: number[] }>(
        "/projects/" + projectId + "/knowledge",
      ),
    ])
      .then(([all, association]) => {
        setCollections(all.items.filter((c) => !c.is_project));
        setLinked(association.linked_collection_ids);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      ++loadSequence.current;
      locateAbort.current?.abort();
    };
  }, [projectId, reload]);
  const running =
    state?.reports.some((r) =>
      ["waiting", "pending", "running"].includes(r.status),
    ) ?? false;
  const processingFiles =
    state?.sources.some((source) => source.state === "processing") ?? false;
  useEffect(() => {
    if (!running && !processingFiles) return;
    const timer = setInterval(() => {
      void reload().catch((e: Error) => setError(e.message));
    }, 3000);
    return () => clearInterval(timer);
  }, [running, processingFiles, reload]);

  // 接口仅发布已核实成果；模块尚未完成时同样允许定位，避免失败后已有成果无法核对。
  const refs = useMemo(
    () => [
      ...(report?.modules.flatMap((m) =>
        m.items.flatMap((i) => i.values.flatMap((v) => v.citations)),
      ) ?? []),
      ...answerRefs,
    ],
    [report, answerRefs],
  );
  const locate = useCallback(async (ref: Citation) => {
    locateAbort.current?.abort();
    const controller = new AbortController();
    locateAbort.current = controller;
    try {
      const resolved = await resolveCitation(ref, controller.signal);
      if (!controller.signal.aborted) {
        setSelected(resolved);
        setMobileDocument(true);
      }
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "原文无法打开");
    }
  }, []);
  const perform = async (action: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
      await reload().catch(() =>
        setError("操作已提交，刷新状态失败，请重试刷新。"),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="workspace analysis-workspace">
      <AppRail />
      <header className="workspace-heading">
        <Link
          href="/projects"
          className="back-button"
          aria-label="返回项目空间"
        >
          <Icon name="back" size={16} />
        </Link>
        <div className="min-w-0">
          <p className="text-xs text-slate-400">项目空间 / 综合分析</p>
          <h1>{name}</h1>
        </div>
        <div className="ml-auto flex shrink-0 gap-2">
          <Link
            href={"/projects/" + projectId + "?view=fields"}
            className={BUTTON_CLASS}
          >
            字段复核
          </Link>
          <Link
            href={"/projects/" + projectId + "/files"}
            className={BUTTON_CLASS}
          >
            文件管理
          </Link>
        </div>
      </header>
      <main id="main-content" className="analysis-main" tabIndex={-1}>
        {error && (
          <Alert
            className="mb-3"
            type="error"
            showIcon
            title={error}
            action={
              <Button
                size="small"
                onClick={() => {
                  setError(null);
                  void reload().catch((e: Error) => setError(e.message));
                }}
              >
                刷新状态
              </Button>
            }
            closable
            onClose={() => setError(null)}
          />
        )}
        <div className="analysis-command-bar">
          <Segmented
            aria-label="分析视图"
            value={tab}
            onChange={setTab}
            options={[
              { value: "report", label: "分析报告" },
              { value: "ask", label: "项目问答" },
            ]}
          />
          <span className="analysis-file-count">
            全部 {state?.sources.length ?? 0} 份材料共同分析
          </span>
          <Button
            type="primary"
            htmlType="submit"
            disabled={busy || running || !category || !state?.sources.length}
            onClick={() =>
              void perform(async () => {
                await knowledgeRequest(
                  "/projects/" + projectId + "/analysis/settings",
                  "PUT",
                  {
                    category,
                    topics,
                    lots: lots.map(({ id, category, topics }) => ({
                      id,
                      category,
                      topics,
                    })),
                  },
                );
                const result = await knowledgeRequest<{ id: number }>(
                  "/projects/" + projectId + "/analysis",
                  "POST",
                  { allow_partial: allowPartial },
                );
                chosenReport.current = result.id;
                setTab("report");
              })
            }
          >
            {running ? "分析任务进行中" : report ? "更新分析" : "开始分析"}
          </Button>
        </div>
        <details className="analysis-options" open={!report || undefined}>
          <summary>
            分析范围与设置{" "}
            <span>{state?.categories[category] ?? "请先选择项目类别"}</span>
          </summary>
          <div className="analysis-options-body">
            <fieldset>
              <legend>项目类别</legend>
              <div className="flex flex-wrap gap-4">
                {Object.entries(state?.categories ?? {}).map(([key, label]) => (
                  <label key={key}>
                    <input
                      type="radio"
                      name="category"
                      checked={category === key}
                      onChange={() => setCategory(key)}
                    />{" "}
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>附加专题</legend>
              <div className="flex flex-wrap gap-4">
                {Object.entries(state?.topics ?? {}).map(([key, label]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={topics.includes(key)}
                      onChange={(e) =>
                        setTopics(
                          e.target.checked
                            ? [...topics, key]
                            : topics.filter((t) => t !== key),
                        )
                      }
                    />{" "}
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            {lots.length > 0 && (
              <fieldset>
                <legend>标段类别与专题</legend>
                {lots.map((lot, index) => (
                  <div
                    className="mb-3 flex flex-wrap items-center gap-3"
                    key={lot.id}
                  >
                    <span>{lot.name}</span>
                    <Select<string>
                      aria-label={lot.name + "类别"}
                      value={String(lot.category ?? "")}
                      onChange={(selectedValue) =>
                        setLots(
                          lots.map((v, i) =>
                            i === index
                              ? { ...v, category: selectedValue || null }
                              : v,
                          ),
                        )
                      }
                    >
                      <Select.Option value="">继承项目类别</Select.Option>
                      {Object.entries(state?.categories ?? {}).map(
                        ([key, label]) => (
                          <Select.Option key={key} value={String(key)}>
                            {label}
                          </Select.Option>
                        ),
                      )}
                    </Select>
                    <label>
                      <input
                        type="checkbox"
                        checked={lot.topics === null}
                        onChange={(e) =>
                          setLots(
                            lots.map((v, i) =>
                              i === index
                                ? { ...v, topics: e.target.checked ? null : [] }
                                : v,
                            ),
                          )
                        }
                      />{" "}
                      继承项目专题
                    </label>
                    {lot.topics !== null &&
                      Object.entries(state?.topics ?? {}).map(
                        ([key, label]) => (
                          <label key={key}>
                            <input
                              type="checkbox"
                              checked={lot.topics?.includes(key) ?? false}
                              onChange={(e) =>
                                setLots(
                                  lots.map((v, i) =>
                                    i === index
                                      ? {
                                          ...v,
                                          topics: e.target.checked
                                            ? [...(v.topics ?? []), key]
                                            : (v.topics?.filter(
                                                (t) => t !== key,
                                              ) ?? []),
                                        }
                                      : v,
                                  ),
                                )
                              }
                            />{" "}
                            {label}
                          </label>
                        ),
                      )}
                  </div>
                ))}
              </fieldset>
            )}
            <label className="block">
              <input
                type="checkbox"
                checked={allowPartial}
                onChange={(e) => setAllowPartial(e.target.checked)}
              />{" "}
              文件未全部就绪时，先分析可用材料并标明缺失
            </label>
            <div className="source-coverage">
              {state?.sources.map((source) => (
                <span
                  key={source.source_id}
                  data-state={source.state}
                  title={source.error_message ?? source.file_name}
                >
                  <span className="truncate">{source.file_name}</span>
                  <b>{STATE_LABELS[source.state] ?? source.state}</b>
                </span>
              ))}
            </div>
            {state?.sources
              .filter((source) => ["failed", "partial"].includes(source.state))
              .map((source) => (
                <div key={source.source_id} className="notice">
                  <span>
                    {source.file_name}：
                    {source.error_message ?? "原文未完整解析"}
                  </span>
                  <Button
                    htmlType="submit"
                    disabled={busy}
                    onClick={() =>
                      void perform(() =>
                        knowledgeRequest(
                          "/knowledge/sources/" + source.source_id + "/process",
                          "POST",
                          {},
                        ),
                      )
                    }
                  >
                    重新处理
                  </Button>
                </div>
              ))}
            {collections.length > 0 && (
              <fieldset>
                <legend>分析与问答参考知识库</legend>
                <p className="mb-2 text-xs text-slate-500">
                  关联资料可供各专题和问答检索参考；本项目要求仍以项目材料为依据。
                </p>
                <div className="flex flex-wrap gap-4">
                  {collections.map((collection) => (
                    <label key={collection.id}>
                      <input
                        type="checkbox"
                        disabled={busy}
                        checked={linked.includes(collection.id)}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...linked, collection.id]
                            : linked.filter((i) => i !== collection.id);
                          void perform(async () => {
                            await knowledgeRequest(
                              "/projects/" +
                                projectId +
                                "/knowledge/collections",
                              "PUT",
                              { collection_ids: next },
                            );
                            setLinked(next);
                          });
                        }}
                      />{" "}
                      {collection.name}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </div>
        </details>
        {report?.stale && (
          <p className="notice my-2">
            项目材料或分析设置已变化。这份报告保留原版本依据，请更新分析。
          </p>
        )}
        <div className="analysis-mobile-switch">
          <button
            aria-pressed={!mobileDocument}
            onClick={() => setMobileDocument(false)}
          >
            分析内容
          </button>
          <button
            aria-pressed={mobileDocument}
            disabled={!selected}
            onClick={() => setMobileDocument(true)}
          >
            引用原文
          </button>
        </div>
        <div className="analysis-split" data-document={mobileDocument}>
          <section className="analysis-content">
            <div hidden={tab !== "ask"}>
              <QuestionPanel
                endpoint={"/projects/" + projectId + "/knowledge/ask"}
                collectionIds={linked}
                onLocate={(ref) => void locate(ref)}
                onCitations={setAnswerRefs}
              />
            </div>
            <div hidden={tab !== "report"}>
              {!report ? (
                <div className="empty-state">
                  <span className="empty-icon">
                    <Icon name="scan" size={28} />
                  </span>
                  <h2>把分散的条款，汇成一份有据可查的报告</h2>
                  <p>
                    选择类别后开始分析。项目内的招标文件、澄清、补遗和附件会一并核对。
                  </p>
                  {!state && <p role="status">正在加载资料…</p>}
                </div>
              ) : (
                <>
                  <div className="report-heading">
                    <div>
                      <p className="text-xs text-slate-400">项目综合报告</p>
                      <h2>{STATE_LABELS[report.status] ?? report.status}</h2>
                    </div>
                    <Select<string>
                      aria-label="选择报告版本"
                      value={String(report.id)}
                      onChange={(selectedValue) => {
                        chosenReport.current = Number(selectedValue);
                        setSelected(null);
                        setActiveItem(undefined);
                        setActiveModuleId(null);
                        void reload().catch((caught: Error) =>
                          setError(caught.message),
                        );
                      }}
                    >
                      {state?.reports.map((r) => (
                        <Select.Option key={r.id} value={String(r.id)}>
                          报告 #{r.id} · {STATE_LABELS[r.status] ?? r.status}
                        </Select.Option>
                      ))}
                    </Select>
                  </div>
                  {report.coverage.mode === "agent_research" && (
                    <p className="mb-3 text-sm text-slate-500">
                      已完成{" "}
                      {
                        report.modules.filter((m) => m.status === "completed")
                          .length
                      }{" "}
                      / {report.modules.length} 个专题 · 已保存{" "}
                      {report.modules.reduce(
                        (count, module) => count + module.items.length,
                        0,
                      )}{" "}
                      项成果
                    </p>
                  )}
                  {report.coverage.partial && (
                    <p className="notice mb-3">
                      本报告覆盖不完整，请在范围设置中核对缺失或部分解析的文件。
                    </p>
                  )}
                  {report.status === "waiting" && (
                    <p className="notice mb-3">
                      正在等待本次全部文件可用。请到文件管理查看失败原因；需要先分析可用材料时，可取消本次任务后勾选部分分析。
                    </p>
                  )}
                  {report.error_message && (
                    <p role="alert" className="notice mb-3">
                      {report.error_message}
                    </p>
                  )}
                  {report.runtime_retired && (
                    <p className="notice mb-3">
                      该报告由已下线的旧解析流程生成，仅供查看；需要最新分析请重新发起。
                    </p>
                  )}
                  {["waiting", "pending", "running"].includes(
                    report.status,
                  ) && (
                    <Button
                      htmlType="submit"
                      className={" mb-3"}
                      disabled={busy}
                      onClick={() =>
                        void perform(() =>
                          knowledgeRequest(
                            "/analysis/reports/" + report.id + "/cancel",
                            "POST",
                            {},
                          ),
                        )
                      }
                    >
                      取消任务
                    </Button>
                  )}
                  {["failed", "partial", "canceled"].includes(report.status) &&
                    !report.runtime_retired &&
                    report.modules.some((module) =>
                      ["failed", "canceled"].includes(module.status),
                    ) && (
                      <Button
                        htmlType="submit"
                        className={" mb-3"}
                        disabled={busy || running}
                        onClick={() =>
                          void perform(() =>
                            knowledgeRequest(
                              "/analysis/reports/" + report.id + "/retry",
                              "POST",
                              {},
                            ),
                          )
                        }
                      >
                        补跑未完成模块
                      </Button>
                    )}
                  {["failed", "canceled"].includes(report.status) &&
                    !report.runtime_retired &&
                    !report.modules.length && (
                      <Button
                        htmlType="submit"
                        className={" mb-3"}
                        disabled={busy || running}
                        onClick={() =>
                          void perform(() =>
                            knowledgeRequest(
                              "/analysis/reports/" + report.id + "/retry",
                              "POST",
                              {},
                            ),
                          )
                        }
                      >
                        重试分析
                      </Button>
                    )}
                  {["failed", "partial", "canceled", "completed"].includes(
                    report.status,
                  ) &&
                    !report.runtime_retired &&
                    !!report.modules.length && (
                      <Button
                        htmlType="submit"
                        className={" mb-3"}
                        disabled={busy || running}
                        onClick={() =>
                          void perform(() =>
                            knowledgeRequest(
                              "/analysis/reports/" + report.id + "/retry",
                              "POST",
                              {
                                module_keys: report.modules.map(
                                  (module) => module.module_key,
                                ),
                              },
                            ),
                          )
                        }
                      >
                        重新解析全部专题
                      </Button>
                    )}
                  {!!report.summary?.length && (
                    <details className="report-module mb-4">
                      <summary className="cursor-pointer text-sm font-medium">
                        综合字段 · {report.summary.length} 项
                      </summary>
                      <p className="my-3 text-xs text-slate-500">
                        合并重复事项，保留各份来源与不同结论。详细专题见下方。
                      </p>
                      <ModuleMarkdown
                        items={report.summary.map((item) => ({
                          ...item,
                          id: "summary-" + item.id,
                        }))}
                        activeId={activeItem}
                        onLocate={(ref) => void locate(ref)}
                      />
                    </details>
                  )}
                  {(() => {
                    // 模块标签按后端调度顺序（module.id）排列，与 worker 日志一致，便于对照运行记录排查。
                    const modules = report.modules;
                    const firstCompleted =
                      modules.find((m) => m.items.length > 0)?.id ??
                      modules.find((m) => m.status === "completed")?.id;
                    const currentId = modules.some(
                      (m) => m.id === activeModuleId,
                    )
                      ? activeModuleId
                      : activeModuleId === null && firstCompleted !== undefined
                        ? firstCompleted
                        : (firstCompleted ?? modules[0]?.id);
                    const current = modules.find((m) => m.id === currentId);
                    if (!modules.length) return null;
                    return (
                      <>
                        <Tabs
                          activeKey={String(currentId)}
                          onChange={(id) => setActiveModuleId(Number(id))}
                          items={modules.map((module) => ({
                            key: String(module.id),
                            label: (
                              <span className="flex flex-col items-start">
                                <span>{module.title}</span>
                                <small className="module-tab-status">
                                  {module.status === "completed"
                                    ? `${module.items.length} 项`
                                    : (STATE_LABELS[module.status] ??
                                      module.status)}
                                </small>
                              </span>
                            ),
                            children:
                              module.id === currentId && current ? (
                                <section className="report-module">
                                  <div className="report-module-heading">
                                    <h3>{current.title}</h3>
                                    <span>
                                      {STATE_LABELS[current.status] ??
                                        current.status}
                                    </span>
                                  </div>
                                  {!!current.runs?.length && (
                                    <details className="mb-3 text-xs text-slate-500">
                                      <summary className="cursor-pointer">
                                        运行记录 · 第{" "}
                                        {current.runs.at(-1)?.attempt} 次
                                      </summary>
                                      <ul className="mt-2 space-y-2">
                                        {current.runs.map((run) => (
                                          <li key={run.id}>
                                            第 {run.attempt} 次 ·{" "}
                                            {STATE_LABELS[run.status] ??
                                              run.status}{" "}
                                            · 模型请求 {run.model_calls}/
                                            {run.limits.max_model_calls} ·
                                            工具调用 {run.tool_calls}/
                                            {run.limits.max_tool_calls} ·
                                            单次输出上限{" "}
                                            {run.limits.max_output_tokens} token
                                            {run.started_at && (
                                              <>
                                                {" "}
                                                · 开始于{" "}
                                                {new Date(
                                                  run.started_at,
                                                ).toLocaleTimeString("zh-CN")}
                                              </>
                                            )}
                                            {run.error_message && (
                                              <p className="mt-1 text-red-600">
                                                {run.error_message}
                                              </p>
                                            )}
                                          </li>
                                        ))}
                                      </ul>
                                    </details>
                                  )}
                                  {current.status === "failed" && (
                                    <div className="notice">
                                      <span>{current.error_message}</span>
                                      {!report.runtime_retired && (
                                        <Button
                                          htmlType="submit"
                                          disabled={busy || running}
                                          onClick={() =>
                                            void perform(() =>
                                              knowledgeRequest(
                                                "/analysis/reports/" +
                                                  report.id +
                                                  "/retry",
                                                "POST",
                                                {
                                                  module_keys: [
                                                    current.module_key,
                                                  ],
                                                },
                                              ),
                                            )
                                          }
                                        >
                                          补跑本模块
                                        </Button>
                                      )}
                                    </div>
                                  )}
                                  {current.status === "completed" &&
                                    !report.runtime_retired && (
                                      <p className="mb-3">
                                        <Button
                                          htmlType="submit"
                                          disabled={busy || running}
                                          onClick={() =>
                                            void perform(() =>
                                              knowledgeRequest(
                                                "/analysis/reports/" +
                                                  report.id +
                                                  "/retry",
                                                "POST",
                                                {
                                                  module_keys: [
                                                    current.module_key,
                                                  ],
                                                },
                                              ),
                                            )
                                          }
                                        >
                                          重新解析本专题
                                        </Button>
                                      </p>
                                    )}
                                  {current.items.length > 0 ? (
                                    <>
                                      {current.status !== "completed" && (
                                        <p
                                          className="my-3 text-sm text-slate-500"
                                          role="status"
                                        >
                                          已保存 {current.items.length}{" "}
                                          项核实成果。本专题尚未完成，以下内容不代表完整分析；补跑会保留这些成果。
                                        </p>
                                      )}
                                      <ModuleMarkdown
                                        items={current.items}
                                        activeId={activeItem}
                                        onLocate={(ref) => void locate(ref)}
                                      />
                                    </>
                                  ) : (
                                    <p className="py-3 text-sm text-slate-500">
                                      {current.status === "completed"
                                        ? "当前检索未找到该主题的明确要求。"
                                        : current.status === "pending"
                                          ? "排队等待分析…"
                                          : current.status === "canceled"
                                            ? "本模块已停止，暂无已核实成果。"
                                            : current.status === "failed"
                                              ? "本次尚无通过校验的成果。"
                                              : "正在检索与核对原文…"}
                                    </p>
                                  )}
                                </section>
                              ) : null,
                          }))}
                        />
                      </>
                    );
                  })()}
                </>
              )}
            </div>
          </section>
          <aside className="analysis-document">
            {selected ? (
              <CitationViewer
                key={selected.version_id + ":" + selected.parse_run_id}
                selected={selected}
                citations={refs.includes(selected) ? refs : [...refs, selected]}
                onReverse={(ref) => {
                  const item = report?.modules
                    .flatMap((m) =>
                      m.items.map((i) => ({ module: m, item: i })),
                    )
                    .find(({ item }) =>
                      item.values.some((value) =>
                        value.citations.some(
                          (r) =>
                            r.source_id === ref.source_id &&
                            r.element_id === ref.element_id,
                        ),
                      ),
                    );
                  if (item) {
                    setTab("report");
                    setActiveModuleId(item.module.id);
                    setActiveItem(item.item.id);
                    setMobileDocument(false);
                    setTimeout(
                      () =>
                        document
                          .getElementById("report-item-" + item.item.id)
                          ?.scrollIntoView({ block: "center" }),
                      0,
                    );
                  }
                }}
              />
            ) : (
              <div className="empty-state">
                <Icon name="book" size={32} />
                <h3>原文就在结论旁边</h3>
                <p>点击报告或回答中的引用，查看对应文件、页码和高亮位置。</p>
              </div>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}
