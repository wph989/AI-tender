"use client";

/**
 * 工作台：左章节树 + 原文 / 右结果的核对界面（设计文档 06 第 2 节）。
 *
 * 高度由外层给（h-full），不再是 h-screen：项目页要在它上面放文件切换条，
 * 自己占满视口会把切换条挤出屏幕。
 *
 * 版本是外部传进来的：工作台不该猜自己该显示哪份文件。
 * 之前按 URL 的 versionId 取数、取不到就退回静态样本，结果是打开系统看到一份
 * 假标书——用户分不清「这是演示数据」还是「我的文件没上传成功」。
 *
 * 三种「点不出一条结果」的情形必须分开说（见 06 第 11 节）：
 *   没解析   → 引导去解析，这里没有可核对的纸；
 *   解析失败 → 说出错误码并给「重新解析」；
 *   抽取失败 / 0 条 → 说出抽取任务的原因并给「重跑抽取」（复用解析产物，代价小得多）。
 * 合成一句「暂无数据」是这个界面此前最大的问题：用户既不知道坏在哪，也没有出路。
 */

import type { PDFDocumentProxy } from "pdfjs-dist";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ResultPanel } from "@/components/results/ResultPanel";
import {
  BUTTON_CLASS,
  DATA_CLASS,
  EYEBROW_CLASS,
  PRIMARY_BUTTON_CLASS,
  RESULT_PANEL_WIDTH,
  SECTION_TITLE_CLASS,
} from "@/components/ui";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";
import { OutlineNav } from "@/components/workbench/OutlineNav";
import { ReviewStatsBar } from "@/components/workbench/ReviewStatsBar";
import { Toolbar } from "@/components/workbench/Toolbar";
import { useEvidenceIndex } from "@/hooks/useEvidenceIndex";
import { useLocate } from "@/hooks/useLocate";
import { usePageRegistry } from "@/hooks/usePageRenderer";
import {
  loadAttempts,
  loadConflicts,
  loadFieldStats,
  loadOutline,
  loadWorkbench,
  reparseVersion,
  rerunExtraction,
  rerunExtractionForVersion,
  resolveConflict,
  submitReview,
  waitForJob,
  type ReviewInput,
  type WorkbenchData,
} from "@/lib/api/client";
import { toBbox } from "@/lib/api/wire";
import { destroyPdfDocument, loadPdfDocument } from "@/lib/pdf/document";
import { rerunModeByField, type RerunButtonMode } from "@/lib/results/rerun";
import { useViewerStore } from "@/lib/store/viewerStore";
import { toActiveEvidence, type EvidenceTarget } from "@/lib/viewer/evidenceIndex";
import type { WireConflict, WireExtraction, WireOutlineItem } from "@/types/workbench";

const EMPTY_EXTRACTIONS: readonly WireExtraction[] = [];

/**
 * 整份重跑的等待上限。单字段重跑是秒级（默认 120s 够），但整份文档要逐字段过一遍模型：
 * 实测 14 个字段约 9 分钟，所以留 20 分钟的窗口。超时也不会丢结果——
 * 提交后界面会立刻刷成「进行中」，pipelineRunning 随之立起、5 秒轮询接管剩下的等待
 * （见下面两处重跑里的即时刷新），这里只是别让提示先说「失败」。
 */
const VERSION_JOB_TIMEOUT_MS = 20 * 60 * 1000;

/** 还在跑的 job 状态：轮询与文案共用同一份判据。 */
const RUNNING_STATUSES = ["pending", "running", "submitted", "parsing", "extracting"];

/** 只看未裁定的冲突：已裁定过的字段不必再在卡片里提示（见 03 第 4.5 节）。 */
function buildConflictMap(items: readonly WireConflict[]): ReadonlyMap<string, WireConflict> {
  const map = new Map<string, WireConflict>();
  for (const item of items) {
    if (item.status === "open") map.set(item.field_key, item);
  }
  return map;
}

interface Props {
  versionId: number;
  /**
   * 复核 / 重跑落定后通知外层：项目文件栏的流水线与待复核数由外层取数，
   * 工作台自己刷不到它（见 ProjectWorkspace）。
   */
  onSettled?: () => void;
}

export function DocumentWorkbench({ versionId, onSettled }: Props) {
  const [data, setData] = useState<WorkbenchData | null>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyExtractionId, setBusyExtractionId] = useState<number | null>(null);
  const [rerunModes, setRerunModes] = useState<Record<string, RerunButtonMode>>({});
  // 「重新加载」要能把 PDF 也重取一遍：pdfUrl 没变时依赖不成立，
  // 所以额外挂一个自增的尝试次数，让加载 PDF 的 effect 重跑。
  const [pdfAttempt, setPdfAttempt] = useState(0);
  const [outline, setOutline] = useState<readonly WireOutlineItem[]>([]);
  const [outlineCollapsed, setOutlineCollapsed] = useState(false);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [conflictsByField, setConflictsByField] = useState<ReadonlyMap<string, WireConflict>>(
    () => new Map<string, WireConflict>(),
  );
  // 整份重跑的忙碌标记：与单字段重跑分开，否则两种按钮会互相点亮
  const [versionBusy, setVersionBusy] = useState<"extract" | "reparse" | null>(null);
  // 「重新解析」的后果横幅：先摆出代价，确认后才提交
  const [reparsePending, setReparsePending] = useState(false);
  // 复核与重跑都会改变统计；自增这个令牌让统计条重新取数
  const [statsToken, setStatsToken] = useState(0);

  const registry = usePageRegistry();
  const { locate } = useLocate(registry);
  const index = useEvidenceIndex(data?.extractions ?? EMPTY_EXTRACTIONS);

  const notice = useViewerStore((state) => state.notice);
  const setNotice = useViewerStore((state) => state.setNotice);
  const requestJump = useViewerStore((state) => state.requestJump);
  const currentPage = useViewerStore((state) => state.currentPage);

  // 统计是旁路：取不到就回落「全部显示重跑按钮」，不能让它挡住结果面板。
  const refreshStats = useCallback(async () => {
    try {
      setRerunModes(rerunModeByField(await loadFieldStats()));
    } catch {
      setRerunModes({});
    }
  }, []);

  const refreshWorkbench = useCallback(async () => {
    const loaded = await loadWorkbench(versionId);
    setData(loaded);
    setLoadError(null);
    // 统计随每次刷新一起重取：否则复核完计数器还停在旧值上，看起来像没生效
    setStatsToken((value) => value + 1);
    void refreshStats();
    // 章节树与跨文件冲突也是旁路：任一取不到都不该让工作台打不开
    void loadOutline(versionId)
      .then((items) => setOutline(items))
      .catch(() => setOutline([]));
    if (loaded.projectId === null) {
      setConflictsByField(new Map<string, WireConflict>());
    } else {
      void loadConflicts(loaded.projectId)
        .then((items) => setConflictsByField(buildConflictMap(items)))
        .catch(() => setConflictsByField(new Map<string, WireConflict>()));
    }
    return loaded;
  }, [refreshStats, versionId]);

  /**
   * 变更落定后的统一收尾：重取工作台，再通知外层重取项目。
   *
   * 5 秒轮询不经过它——轮询只刷工作台自己，顺带每 5 秒打一遍项目接口没有必要。
   */
  const settle = useCallback(async () => {
    await refreshWorkbench();
    onSettled?.();
  }, [onSettled, refreshWorkbench]);

  useEffect(() => {
    let alive = true;
    refreshWorkbench()
      .then((loaded) => {
        if (alive) setData(loaded);
      })
      .catch((error: unknown) => {
        if (alive) setLoadError(error instanceof Error ? error.message : "文档数据加载失败");
      });
    return () => {
      alive = false;
    };
  }, [refreshWorkbench]);

  // PDF 基座单独加载：原文区失败时，结果面板仍能呈现可读的接口错误。
  const pdfUrl = data?.pdfUrl;
  useEffect(() => {
    if (pdfUrl === undefined) return;
    let alive = true;
    let loaded: PDFDocumentProxy | null = null;
    loadPdfDocument(pdfUrl)
      .then((document) => {
        if (!alive) {
          destroyPdfDocument(document);
          return;
        }
        loaded = document;
        setPdf(document);
      })
      .catch((error: unknown) => {
        if (alive) setLoadError(error instanceof Error ? error.message : "PDF 加载失败");
      });
    return () => {
      alive = false;
      if (loaded !== null) destroyPdfDocument(loaded);
    };
  }, [pdfUrl, pdfAttempt]);

  // 解析/抽取在跑时自动刷新：点完重跑只能靠手动刷页面等结果，是最容易被骂的一处
  const pipelineRunning =
    data !== null &&
    [data.parseStatus, data.extractionStatus].some(
      (status) => status !== null && RUNNING_STATUSES.includes(status),
    );
  useEffect(() => {
    if (!pipelineRunning) return;
    const timer = window.setInterval(() => {
      void refreshWorkbench().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [pipelineRunning, refreshWorkbench]);

  const errorMessage = (error: unknown, fallback: string): string =>
    error instanceof Error ? error.message : fallback;

  const handleLocate = useCallback(
    (target: EvidenceTarget) => {
      void locate(toActiveEvidence(target));
    },
    [locate],
  );

  const handleViewerError = useCallback(
    (message: string) => {
      setNotice(message);
    },
    [setNotice],
  );

  /**
   * 点章节：跳到该章所在页，并把标题块高亮出来。
   *
   * 高亮复用原文的定位通道（activeEvidence），但 extractionId 用 -1 这个哨兵值——
   * 它不是任何一条结果，右侧的反向联动因此会正确地忽略它（见 ResultPanel 的说明）。
   * 找不到标题块坐标时只跳页：跳到那一章仍是这个动作的主要目的。
   */
  const handleOutlineSelect = useCallback(
    (item: WireOutlineItem) => {
      const block = (data?.blocksByPage[String(item.page_no)] ?? []).find(
        (candidate) => candidate.anchor === item.anchor,
      );
      const bbox = block === undefined ? null : toBbox(block.bbox);
      if (bbox === null) {
        requestJump(item.page_no);
        return;
      }
      void locate({
        extractionId: -1,
        anchor: item.anchor,
        pageNo: item.page_no,
        bbox,
        label: item.text,
      });
    },
    [data, locate, requestJump],
  );

  const handleReview = useCallback(
    async (extraction: WireExtraction, input: ReviewInput): Promise<boolean> => {
      setBusyExtractionId(extraction.id);
      setNotice(null);
      try {
        await submitReview(extraction.instance_id, input);
        await settle();
        return true;
      } catch (error: unknown) {
        setNotice(errorMessage(error, "复核提交失败"));
        return false;
      } finally {
        setBusyExtractionId(null);
      }
    },
    [settle, setNotice],
  );

  const handleRerun = useCallback(
    async (extraction: WireExtraction, hint: string | null): Promise<boolean> => {
      setBusyExtractionId(extraction.id);
      setNotice(null);
      try {
        const queued = await rerunExtraction(extraction.id, hint);
        setNotice("字段重跑已提交，正在等待结果…");
        const job = await waitForJob(queued.job_id);
        if (job.status === "failed" || job.status === "canceled") {
          throw new Error(job.error_message ?? "字段重跑失败");
        }
        await settle();
        setNotice(null);
        return true;
      } catch (error: unknown) {
        setNotice(errorMessage(error, "字段重跑失败"));
        return false;
      } finally {
        setBusyExtractionId(null);
      }
    },
    [settle, setNotice],
  );

  /**
   * 重跑抽取：复用最近一次解析产物，不重建锚点、不作废已确认的结果。
   *
   * 为什么不能拿 POST /projects/{id}/rerun 代替：那个端点是从**已有结果行**里筛候选的，
   * 一条结果都没有时它只返回 queued = 0——正是这里要救的场景。
   */
  const handleExtractRerun = useCallback(async () => {
    setVersionBusy("extract");
    setNotice("已提交重跑抽取，正在等待结果…");
    try {
      const queued = await rerunExtractionForVersion(versionId);
      // 提交后立刻刷一次：界面据此显示「正在抽取」、pipelineRunning 变成真，
      // 5 秒轮询才会接管剩下的等待；否则整段时间里界面停在失败态。
      // 刷新失败不判定为提交失败——任务已经落库，下一轮轮询会自愈。
      void refreshWorkbench().catch(() => undefined);
      const job = await waitForJob(queued.job_id, VERSION_JOB_TIMEOUT_MS);
      if (job.status === "failed" || job.status === "canceled") {
        throw new Error(job.error_message ?? "重跑抽取失败");
      }
      await settle();
      setNotice(null);
    } catch (error: unknown) {
      setNotice(errorMessage(error, "重跑抽取失败"));
    } finally {
      setVersionBusy(null);
    }
  }, [settle, setNotice, versionId]);

  /**
   * 重新解析：锚点全部重建、已确认结果全部打回复核。代价比前者重一个量级，
   * 所以调用点必须先过后果横幅（reparsePending），不能一个点击就直接提交。
   */
  const handleReparse = useCallback(async () => {
    setReparsePending(false);
    setVersionBusy("reparse");
    setNotice("已提交重新解析，锚点将全部重建…");
    try {
      const queued = await reparseVersion(versionId, {
        // 沿用上一次的档位：重新解析的目的是「修好这一次」，不是顺手换档
        tier: (data?.parseTier ?? "standard") as "flash" | "basic" | "standard" | "advanced",
        ocrMode: "auto",
        reason: "用户在结果面板发起重新解析",
      });
      // 同「重跑抽取」：先把界面切到进行中，轮询才会接管这段更漫长的等待。
      void refreshWorkbench().catch(() => undefined);
      const job = await waitForJob(queued.job_id, VERSION_JOB_TIMEOUT_MS);
      if (job.status === "failed" || job.status === "canceled") {
        throw new Error(job.error_message ?? "重新解析失败");
      }
      await settle();
      setNotice(null);
    } catch (error: unknown) {
      setNotice(errorMessage(error, "重新解析失败"));
    } finally {
      setVersionBusy(null);
    }
  }, [data, settle, setNotice, versionId]);

  /** 结果卡内的跨文件冲突裁定：裁定完立刻重取，卡片上的候选值随之消失。 */
  const handleResolveConflict = useCallback(
    async (conflictId: number, resolvedId: number) => {
      setNotice(null);
      try {
        await resolveConflict(conflictId, { action: "resolve", resolved_id: resolvedId });
        await settle();
      } catch (error: unknown) {
        setNotice(errorMessage(error, "冲突裁定失败"));
      }
    },
    [settle, setNotice],
  );

  // 批量确认逐条提交（后端是一次一条的复核接口），失败计数而不是中断：
  // 中途停下会让用户不知道到底确认了哪些，重刷一次就能看到真实状态。
  const handleBatchConfirm = useCallback(
    async (items: readonly WireExtraction[]): Promise<void> => {
      setNotice(`正在批量确认 ${items.length} 项…`);
      let failed = 0;
      for (const item of items) {
        try {
          await submitReview(item.instance_id, {
            attempt_id: item.id,
            action: "confirm",
            review_mode: "batch",
          });
        } catch {
          failed += 1;
        }
      }
      await settle();
      setNotice(failed > 0 ? `批量确认完成，${failed} 项失败，请重试` : null);
    },
    [settle, setNotice],
  );

  const reloadAll = useCallback(() => {
    setLoadError(null);
    setPdfAttempt((value) => value + 1);
    void refreshWorkbench().catch((error: unknown) => {
      setLoadError(error instanceof Error ? error.message : "重新加载失败");
    });
  }, [refreshWorkbench]);

  const parseDone =
    data !== null && (data.parseStatus === "completed" || data.parseStatus === "partial");
  const parseFailed =
    data !== null && (data.parseStatus === "failed" || data.parseStatus === "canceled");
  const parseRunning =
    data !== null && data.parseStatus !== null && RUNNING_STATUSES.includes(data.parseStatus);
  const extractFailed =
    data !== null &&
    (data.extractionStatus === "failed" || data.extractionStatus === "canceled");
  const extractRunning =
    data !== null && data.extractionStatus !== null && RUNNING_STATUSES.includes(data.extractionStatus);
  const noResults = data !== null && data.extractions.length === 0;
  const confirmedCount =
    data === null ? 0 : data.extractions.filter((item) => item.status === "verified").length;
  const filesHref = data?.projectId != null ? "/projects/" + data.projectId + "/files" : "/projects";

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-slate-100">
      <Toolbar
        pageCount={data?.pages.length ?? 0}
        projectId={data?.projectId ?? null}
        onNotice={setNotice}
      />

      {notice !== null && (
        <div className="flex items-center gap-3 border-b border-amber-200 bg-amber-50 py-1.5 pr-3 pl-4">
          <span aria-hidden className="h-3.5 w-[4px] shrink-0 bg-amber-400" />
          <span className="flex-1 text-[13px] text-amber-900">{notice}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="rounded-[2px] px-1.5 py-0.5 text-[13px] text-amber-700 hover:bg-amber-100"
          >
            关闭
          </button>
        </div>
      )}

      {loadError !== null ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="max-w-md border border-rose-200 bg-white px-5 py-4">
            <h2 className={SECTION_TITLE_CLASS}>加载失败</h2>
            <p className="mt-2 text-[13px] leading-5 text-rose-700">{loadError}</p>
            <p className="mt-2 text-[13px] leading-5 text-slate-500">
              原文与结果分别取自两个接口，其中一个失败不影响另一个；重试会一起再取一次。
            </p>
            <button type="button" className={PRIMARY_BUTTON_CLASS + " mt-3"} onClick={reloadAll}>
              重新加载
            </button>
          </div>
        </div>
      ) : data === null || pdf === null ? (
        <div className="flex flex-1 items-center justify-center text-[14px] text-slate-500">
          正在加载原文与结果…
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <ReviewStatsBar
            projectId={data.projectId}
            reviewOnly={reviewOnly}
            onReviewModeChange={setReviewOnly}
            refreshToken={statsToken}
          />

          {/* 后果横幅：重新解析的代价必须先说清楚，再让用户按下去 */}
          {reparsePending && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rose-200 bg-rose-50 py-2 pr-3 pl-4">
              <span aria-hidden className="h-4 w-[4px] shrink-0 bg-rose-500" />
              <p className="text-[13px] text-rose-800">
                重新解析会重建全部锚点（页码与 block 编号都可能变），此前{" "}
                <span className={DATA_CLASS + " font-medium"}>{confirmedCount}</span>{" "}
                条已确认结果需要重新复核。
              </p>
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  className={PRIMARY_BUTTON_CLASS}
                  disabled={versionBusy !== null}
                  onClick={() => void handleReparse()}
                >
                  {versionBusy === "reparse" ? "提交中…" : "确认重新解析"}
                </button>
                <button
                  type="button"
                  className={BUTTON_CLASS}
                  disabled={versionBusy !== null}
                  onClick={() => setReparsePending(false)}
                >
                  取消
                </button>
              </div>
            </div>
          )}

          <div className="flex min-h-0 flex-1">
            <OutlineNav
              items={outline}
              currentPage={currentPage}
              collapsed={outlineCollapsed}
              onToggle={() => setOutlineCollapsed((value) => !value)}
              onSelect={handleOutlineSelect}
            />

            <div className="min-w-0 flex-1">
              <DocumentViewer
                pdf={pdf}
                pages={data.pages}
                index={index}
                registry={registry}
                onError={handleViewerError}
                onLocate={handleLocate}
              />
            </div>

            {!noResults ? (
              <ResultPanel
                extractions={data.extractions}
                index={index}
                rerunModes={rerunModes}
                projectId={data.projectId}
                busyExtractionId={busyExtractionId}
                reviewOnly={reviewOnly}
                onReviewModeChange={setReviewOnly}
                conflictsByField={conflictsByField}
                onLocate={handleLocate}
                onReview={handleReview}
                onRerun={handleRerun}
                onResolveConflict={handleResolveConflict}
                onBatchConfirm={handleBatchConfirm}
                onRefresh={async () => {
                  await refreshWorkbench();
                }}
                onNotice={setNotice}
                onLoadAttempts={loadAttempts}
              />
            ) : parseFailed ? (
              /* 解析失败：说出错误码 + 给出「重新解析」这条路 */
              <aside
                className={
                  RESULT_PANEL_WIDTH + " shrink-0 overflow-y-auto border-l border-slate-200 bg-white px-5 py-5"
                }
              >
                <p className={EYEBROW_CLASS}>解析结果</p>
                <h2 className="mt-1.5 font-serif text-[19px] leading-[28px] text-rose-700">
                  解析失败
                </h2>
                <div className="mt-3 border border-rose-200 bg-rose-50 px-3 py-2">
                  <p className={DATA_CLASS + " text-[13px] break-words text-rose-800"}>
                    {data.parseError ?? "未提供错误信息"}
                  </p>
                </div>
                <p className="mt-3 text-[14px] leading-[22px] text-slate-600">
                  解析没有产出可用的元素与锚点，所以没有任何字段可抽取。修好上面的原因后重新解析一次；
                  重新解析会重建锚点，此前已确认的结果需要重新复核。
                </p>
                <div className="mt-4 flex flex-col gap-2">
                  <button
                    type="button"
                    className={PRIMARY_BUTTON_CLASS}
                    disabled={versionBusy !== null}
                    onClick={() => setReparsePending(true)}
                  >
                    重新解析
                  </button>
                  <Link href={filesHref} className={BUTTON_CLASS}>
                    去文件管理页查看任务
                  </Link>
                </div>
              </aside>
            ) : !parseDone ? (
              /* 未解析（或正在解析）：这里没有可核对的纸，指路而不是给按钮 */
              <aside
                className={
                  RESULT_PANEL_WIDTH + " shrink-0 overflow-y-auto border-l border-slate-200 bg-white px-5 py-5"
                }
              >
                <p className={EYEBROW_CLASS}>解析结果</p>
                <h2 className="mt-1.5 font-serif text-[19px] leading-[28px] text-slate-900">
                  {parseRunning ? "正在解析原文…" : "这份文件还没有解析"}
                </h2>
                <p className="mt-3 text-[14px] leading-[22px] text-slate-600">
                  {parseRunning
                    ? "解析跑完后这里会自动出现字段结果，不用手动刷新。"
                    : "抽取结果建立在解析产物之上（元素、锚点、页码），没有解析就没有可核对的字段。"}
                </p>
                <div className="mt-4 flex flex-col gap-2">
                  <Link href={filesHref} className={PRIMARY_BUTTON_CLASS}>
                    {parseRunning ? "查看解析进度" : "去文件管理页解析"}
                  </Link>
                </div>
              </aside>
            ) : (
              /* 解析成了但一条结果都没有：主按钮是「重跑抽取」，不是「重新解析」 */
              <aside
                className={
                  RESULT_PANEL_WIDTH + " shrink-0 overflow-y-auto border-l border-slate-200 bg-white px-5 py-5"
                }
              >
                <p className={EYEBROW_CLASS}>解析结果</p>
                <h2 className="mt-1.5 font-serif text-[19px] leading-[28px] text-slate-900">
                  {extractRunning ? "正在抽取…" : extractFailed ? "抽取失败" : "还没有抽取结果"}
                </h2>
                {data.extractionError !== null && (
                  <div className="mt-3 border border-rose-200 bg-rose-50 px-3 py-2">
                    <p className={DATA_CLASS + " text-[13px] break-words text-rose-800"}>
                      {data.extractionError}
                    </p>
                  </div>
                )}
                <p className="mt-3 text-[14px] leading-[22px] text-slate-600">
                  原文已经解析完成（{data.pages.length} 页的元素与锚点都在），但没有任何字段被抽出来。
                  {extractRunning
                    ? "抽取正在跑，跑完这里会自动出结果。"
                    : extractFailed
                      ? "上一次抽取任务失败了。"
                      : "常见原因是还没有配置可用的大模型。"}
                  {" "}
                  「重跑抽取」复用现有解析产物，不会作废已确认的结果。
                </p>
                <div className="mt-4 flex flex-col gap-2">
                  <button
                    type="button"
                    className={PRIMARY_BUTTON_CLASS}
                    disabled={versionBusy !== null || extractRunning}
                    onClick={() => void handleExtractRerun()}
                  >
                    {versionBusy === "extract" ? "重跑中…" : "重跑抽取"}
                  </button>
                  <button
                    type="button"
                    className={BUTTON_CLASS}
                    disabled={versionBusy !== null}
                    onClick={() => setReparsePending(true)}
                  >
                    重新解析
                  </button>
                  <Link href="/settings/models" className={BUTTON_CLASS}>
                    配置供应商与模型
                  </Link>
                </div>
              </aside>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
