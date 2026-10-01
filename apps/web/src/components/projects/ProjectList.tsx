"use client";

/**
 * 项目列表（设计文档 06 第 1 节路由矩阵里的 /projects）。
 *
 * 为什么是通栏卷宗清单而不是卡片墙：项目数量增长后，卡片的固定高度会让一屏只能放
 * 四五个，而这里真正要回答的问题是「哪个项目还有活要干」——那是几个可比较的值
 * （文件数、待复核数、最近活动）的事。清单把它们排在同一条竖线上，眼睛从上往下扫
 * 一列就够了；通栏之后也才容得下「项目号」这种原本无处安放的字段。
 *
 * 为什么行首有一道色条（卷宗脊）：它是全站的签名元素，颜色即状态。有待复核是琥珀、
 * 空项目是灰、没有待办是墨色；一屏扫下来就知道该先点开哪一个，不用逐个读文字。
 * 脊色是「这个项目最紧急的那一件事」，是让人停下来的信号，不是整行状态的完整描述。
 *
 * 搜索框常驻在页头（而不是只在有数据时才出现在清单表头里），并绑定 `/` 聚焦：
 * 「按编号找一个项目」是这一页最高频的动作，不该先滚动、再瞄准。
 *
 * 新建项目按设计文档要求逐个创建，不做批量导入：批量导入要么靠模板文件（多一层格式
 * 门槛），要么在列表里堆一批重名项目（事后没人认得）。
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageShell } from "@/components/PageShell";
import {
  BUTTON_CLASS,
  DATA_CLASS,
  EYEBROW_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECTION_TITLE_CLASS,
} from "@/components/ui";
import { createProject, listProjects } from "@/lib/api/client";
import { formatTime } from "@/lib/format";
import type { WireProject } from "@/types/projects";

/**
 * 行与列头共用同一份列宽：两处各写一份，改一次列宽就会错开一行。
 * 列序：项目号 / 项目 / 文件 / 待复核 / 最近活动 / 入口（卷宗脊是绝对定位，不占轨道）。
 */
const ROW_GRID =
  "grid grid-cols-[7rem_minmax(0,1fr)_4.5rem_5rem_9rem_1.5rem] items-center gap-x-4";

/** 一行 56px：宋体名字 + 负责人两行字刚好放得下，又比 40px 的行更像一份卷宗。 */
const ROW_HEIGHT = "h-14";

/** 一行项目的状态脊：取该项目「最紧急」的那一件事的颜色。 */
/** 脊色的文字解释；脊只有 4px，不给文字就等于让色觉障碍用户全靠猜。 */
function spineHint(project: WireProject): string {
  if ((project.failed_count ?? 0) > 0) return `${project.failed_count} 个文件解析或抽取失败`;
  if ((project.review_count ?? 0) > 0) return `${project.review_count} 项待复核`;
  if ((project.file_count ?? 0) === 0) return "还没有文件";
  return "没有待办";
}

function spineOf(project: WireProject): string {
  // 失败排最前：解析/抽取挂掉的项目最需要被看见。
  // 排到待复核之后，它会混进「还有别的事要干」里被忽略，而它其实是要人去修的。
  if ((project.failed_count ?? 0) > 0) return "bg-rose-600";
  if ((project.review_count ?? 0) > 0) return "bg-amber-400";
  if ((project.file_count ?? 0) === 0) return "bg-slate-300";
  return "bg-slate-900";
}

export function ProjectList() {
  const [projects, setProjects] = useState<WireProject[] | null>(null);
  const [keyword, setKeyword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({ name: "", project_no: "", owner: "" });
  const searchRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async (search: string) => {
    const items = await listProjects(search);
    setProjects(items);
    setError(null);
  }, []);

  useEffect(() => {
    let alive = true;
    reload("")
      .catch((caught: unknown) => {
        if (alive) setError(caught instanceof Error ? caught.message : "加载项目失败");
      });
    return () => {
      alive = false;
    };
  }, [reload]);

  /*
   * `/` 聚焦搜索。
   *
   * 为什么在 window 上监听而不是给输入框加个快捷键组件：这一页没有别的键盘流，
   * 输入框本身也不该知道「自己是这一页的搜索框」。
   * 焦点已经在输入框里时直接放行：项目编号里带斜杠是常事，被吞掉一个字符很烦人。
   */
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
      ) {
        return;
      }
      event.preventDefault();
      searchRef.current?.focus();
      searchRef.current?.select();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const totals = useMemo(() => {
    const items = projects ?? [];
    return {
      files: items.reduce((sum, item) => sum + (item.file_count ?? 0), 0),
      reviews: items.reduce((sum, item) => sum + (item.review_count ?? 0), 0),
      failures: items.reduce((sum, item) => sum + (item.failed_count ?? 0), 0),
    };
  }, [projects]);

  const submit = async () => {
    if (!draft.name.trim() || busy) return;
    setBusy(true);
    try {
      await createProject({
        name: draft.name.trim(),
        project_no: draft.project_no.trim() || null,
        owner: draft.owner.trim() || null,
      });
      setDraft({ name: "", project_no: "", owner: "" });
      setCreating(false);
      await reload(keyword);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "创建项目失败");
    } finally {
      setBusy(false);
    }
  };

  const search = () => {
    void reload(keyword).catch(() => setError("搜索失败"));
  };

  return (
    <PageShell
      eyebrow="项目"
      title="项目"
      description={
        projects === null
          ? "每个项目是一份招标材料（主文件 + 补遗 + 澄清），解析完成后在这里核对抽取结果。"
          : `共 ${projects.length} 个项目 · ${totals.files} 个文件 · ${totals.reviews} 项待复核` +
            (totals.failures > 0 ? ` · ${totals.failures} 个文件失败要重跑` : "") +
            "。点开项目进入工作台，左边原文、右边结果，点结果即可定位出处。"
      }
      actions={
        <>
          {/* 搜索常驻页头：加载中、空项目时它也在，用户不必等列表先出来才能搜。 */}
          <div className="relative">
            <input
              ref={searchRef}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") search();
              }}
              placeholder="按名称或编号搜索"
              aria-label="按名称或编号搜索项目"
              className={INPUT_CLASS + " w-64 pr-7"}
            />
            <span
              aria-hidden
              className={
                DATA_CLASS +
                " pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-[11px] text-slate-400"
              }
            >
              /
            </span>
          </div>
          <button type="button" className={BUTTON_CLASS} onClick={search}>
            搜索
          </button>
          <button
            type="button"
            className={BUTTON_CLASS}
            onClick={() => {
              void reload(keyword).catch(() => setError("刷新失败"));
            }}
          >
            刷新
          </button>
          <button
            type="button"
            className={PRIMARY_BUTTON_CLASS}
            onClick={() => setCreating((open) => !open)}
          >
            {creating ? "取消新建" : "新建项目"}
          </button>
        </>
      }
    >
      {error !== null && (
        <p className="border border-rose-200 bg-rose-50 px-3 py-2 text-[14px] text-rose-700">
          {error}
        </p>
      )}

      {creating && (
        <section className="border border-slate-300 bg-white">
          <div aria-hidden className="h-[4px] bg-amber-400" />
          <div className="px-5 py-4">
            <h2 className={SECTION_TITLE_CLASS}>新建项目</h2>
            <p className="mt-1 text-[13px] leading-5 text-slate-500">
              项目只是一只容器：名称先随便填，文件可以随时增删换版本，编号与负责人之后也能改。
            </p>
            <div className="mt-4 flex flex-wrap items-end gap-4">
              <label className="flex min-w-72 flex-1 flex-col gap-1.5">
                <span className="text-[13px] text-slate-500">项目名称</span>
                <input
                  autoFocus
                  value={draft.name}
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void submit();
                  }}
                  placeholder="例如：某某中心机房改造采购"
                  className={INPUT_CLASS}
                />
              </label>
              <label className="flex w-48 flex-col gap-1.5">
                <span className="text-[13px] text-slate-500">项目编号（选填）</span>
                <input
                  value={draft.project_no}
                  onChange={(event) => setDraft({ ...draft, project_no: event.target.value })}
                  className={INPUT_CLASS}
                />
              </label>
              <label className="flex w-40 flex-col gap-1.5">
                <span className="text-[13px] text-slate-500">负责人（选填）</span>
                <input
                  value={draft.owner}
                  onChange={(event) => setDraft({ ...draft, owner: event.target.value })}
                  className={INPUT_CLASS}
                />
              </label>
              <button
                type="button"
                className={PRIMARY_BUTTON_CLASS + " px-4 py-2"}
                disabled={busy || !draft.name.trim()}
                onClick={() => void submit()}
              >
                {busy ? "正在创建…" : "创建项目"}
              </button>
            </div>
          </div>
        </section>
      )}

      {projects === null && <p className="text-[14px] text-slate-500">正在加载项目…</p>}

      {projects !== null && projects.length === 0 && (
        <div className="border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <p className="font-serif text-[19px] text-slate-900">
            {keyword.trim() ? "没有匹配的项目" : "还没有项目"}
          </p>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate-500">
            {keyword.trim()
              ? "换一个名称或编号的关键词再搜一次；搜索是服务端按名称与编号做模糊匹配。"
              : "建一个项目，再往里上传招标文件；解析完成后就能在原文上核对抽取结果。"}
          </p>
          {!creating && !keyword.trim() && (
            <button
              type="button"
              className={PRIMARY_BUTTON_CLASS + " mt-5 px-4 py-2"}
              onClick={() => setCreating(true)}
            >
              新建项目
            </button>
          )}
        </div>
      )}

      {projects !== null && projects.length > 0 && (
        <section className="border border-slate-200 bg-white">
          <header className="flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-slate-200 px-5 py-3">
            <div>
              <p className={EYEBROW_CLASS}>卷宗清单</p>
              <h2 className={SECTION_TITLE_CLASS + " mt-1"}>项目</h2>
            </div>
            <span className={DATA_CLASS + " pb-0.5 text-[13px] text-slate-400"}>
              {projects.length} 项
            </span>
            {/* 脊色图例：色块对色觉障碍用户等于不存在，文字和颜色必须成对出现。 */}
            <ul className="ml-auto flex items-center gap-4 pb-0.5 text-[13px] text-slate-400">
              <li className="flex items-center gap-1.5">
                <span aria-hidden className="h-[7px] w-[7px] bg-rose-600" />
                有失败
              </li>
              <li className="flex items-center gap-1.5">
                <span aria-hidden className="h-[7px] w-[7px] bg-amber-400" />
                有待复核
              </li>
              <li className="flex items-center gap-1.5">
                <span aria-hidden className="h-[7px] w-[7px] bg-slate-300" />
                空项目
              </li>
              <li className="flex items-center gap-1.5">
                <span aria-hidden className="h-[7px] w-[7px] bg-slate-900" />
                没有待办
              </li>
            </ul>
          </header>

          {/* 列头只出现一次：每行都重复一遍标签，扫视时反而全是字。 */}
          <div
            className={
              "hidden " + ROW_GRID + " border-b border-slate-100 px-5 py-2 text-[13px] text-slate-400 md:grid"
            }
          >
            <span>项目号</span>
            <span>项目</span>
            <span className="text-right">文件</span>
            <span className="text-right">待复核</span>
            <span className="text-right">最近活动</span>
            <span />
          </div>

          <ul>
            {projects.map((project) => (
              <li key={project.id} className="border-b border-slate-100 last:border-b-0">
                <Link
                  href={"/projects/" + project.id}
                  className={
                    "group relative " + ROW_GRID + " " + ROW_HEIGHT + " px-5 transition-colors hover:bg-slate-50"
                  }
                >
                  <span
                    aria-hidden
                    title={spineHint(project)}
                    className={"absolute inset-y-0 left-0 w-[4px] " + spineOf(project)}
                  />
                  <span
                    className={DATA_CLASS + " truncate text-[13px] text-slate-500"}
                    title={project.project_no ?? undefined}
                  >
                    {project.project_no ?? "—"}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-serif text-[15px] leading-[22px] text-slate-900 group-hover:text-sky-800">
                      {project.name}
                    </span>
                    <span className="mt-0.5 block truncate text-[12px] leading-4 text-slate-400">
                      {project.owner ?? "未指定负责人"}
                    </span>
                  </span>
                  <span className={DATA_CLASS + " text-right text-[14px] text-slate-700"}>
                    {project.file_count ?? 0}
                  </span>
                  <span className="text-right">
                    {(project.review_count ?? 0) > 0 ? (
                      <span className={DATA_CLASS + " mark-ink px-1 text-[14px] text-slate-900"}>
                        {project.review_count}
                      </span>
                    ) : (
                      <span className={DATA_CLASS + " text-[14px] text-slate-300"}>—</span>
                    )}
                  </span>
                  <span
                    className="truncate text-right text-[13px] text-slate-500"
                    title={project.last_activity_at ?? project.created_at}
                  >
                    {formatTime(project.last_activity_at ?? project.created_at)}
                  </span>
                  <span
                    aria-hidden
                    className="text-center text-[14px] text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-slate-500"
                  >
                    →
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </PageShell>
  );
}
