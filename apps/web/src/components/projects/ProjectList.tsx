"use client";

/**
 * 项目列表（设计文档 06 第 1 节路由矩阵里的 /projects）。
 *
 * 为什么是清单而不是卡片墙：项目数量增长后，卡片的固定高度会让一屏只能放四五个，
 * 而这里真正要回答的问题是「哪个项目还有活要干」——那是两个数字（文件数、待复核数）的事。
 * 清单把这些可比较的值排在一条竖线上，眼睛从上往下扫一列就够了。
 *
 * 为什么行首有一道色条（卷宗脊）：它是全站的签名元素，颜色即状态。
 * 有文件在跑是琥珀、有待复核是琥珀、全清是墨色、空项目是灰色；
 * 一屏扫下来就知道该先点开哪一个，不用逐个读文字。
 *
 * 新建项目按设计文档要求逐个创建，不做批量导入：批量导入要么靠模板文件（多一层格式门槛），
 * 要么在列表里堆一批重名项目（事后没人认得）。
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageShell } from "@/components/PageShell";
import {
  BUTTON_CLASS,
  DATA_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECTION_TITLE_CLASS,
} from "@/components/ui";
import { createProject, listProjects } from "@/lib/api/client";
import { formatTime } from "@/lib/format";
import type { WireProject } from "@/types/projects";

/** 一行项目的状态脊：待复核优先，其次是有没有文件。 */
function spineOf(project: WireProject): string {
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

  const totals = useMemo(() => {
    const items = projects ?? [];
    return {
      files: items.reduce((sum, item) => sum + (item.file_count ?? 0), 0),
      reviews: items.reduce((sum, item) => sum + (item.review_count ?? 0), 0),
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
          : `共 ${projects.length} 个项目 · ${totals.files} 个文件 · ${totals.reviews} 项待复核。` +
            "点开项目进入工作台，左边原文、右边结果，点结果即可定位出处。"
      }
      actions={
        <>
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
          <div aria-hidden className="h-[3px] bg-amber-400" />
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
          <p className="font-serif text-[19px] text-slate-900">还没有项目</p>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate-500">
            建一个项目，再往里上传招标文件；解析完成后就能在原文上核对抽取结果。
          </p>
          {!creating && (
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
          <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-2.5">
            <h2 className="text-[14px] font-medium text-slate-700">清单</h2>
            <span className={DATA_CLASS + " text-[13px] text-slate-400"}>
              {projects.length} 项
            </span>
            <div className="ml-auto flex items-center gap-2">
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") search();
                }}
                placeholder="按名称或编号搜索"
                aria-label="按名称或编号搜索项目"
                className={INPUT_CLASS + " w-56 py-1"}
              />
              <button type="button" className={BUTTON_CLASS + " py-1"} onClick={search}>
                搜索
              </button>
            </div>
          </header>

          {/* 列头只出现一次：每行都重复一遍标签，扫视时反而全是字。 */}
          <div className="hidden grid-cols-[2rem_minmax(0,1fr)_5rem_5rem_6rem_1.25rem] items-center gap-x-4 border-b border-slate-100 px-4 py-1.5 text-[13px] text-slate-400 md:grid">
            <span>#</span>
            <span>项目</span>
            <span className="text-right">文件</span>
            <span className="text-right">待复核</span>
            <span className="text-right">创建时间</span>
            <span />
          </div>

          <ul>
            {projects.map((project, index) => (
              <li key={project.id} className="border-b border-slate-100 last:border-b-0">
                <Link
                  href={"/projects/" + project.id}
                  className="group relative grid grid-cols-[2rem_minmax(0,1fr)_5rem_5rem_6rem_1.25rem] items-center gap-x-4 px-4 py-3 transition-colors hover:bg-slate-50"
                >
                  <span
                    aria-hidden
                    className={
                      "absolute inset-y-0 left-0 w-[4px] " + spineOf(project)
                    }
                  />
                  <span className={DATA_CLASS + " text-[13px] text-slate-300"}>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-serif text-[15px] leading-6 text-slate-900 group-hover:text-sky-800">
                      {project.name}
                    </span>
                    <span className="mt-0.5 block truncate text-[13px] text-slate-400">
                      {project.project_no ?? "无编号"} · {project.owner ?? "未指定负责人"}
                    </span>
                  </span>
                  <span className="text-right">
                    <span className={DATA_CLASS + " text-[14px] text-slate-700"}>
                      {project.file_count ?? 0}
                    </span>
                    <span className="ml-1 text-[11px] text-slate-400">文件</span>
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
                  <span className="text-right text-[13px] text-slate-400">
                    {formatTime(project.created_at)}
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
