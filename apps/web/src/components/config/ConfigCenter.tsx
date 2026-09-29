"use client";

/**
 * 配置中心页容器（设计文档 08 第 2、5、6 节）。
 *
 * 任何写操作后统一重取"配置项 + 版本列表 + 当前选中版本详情"：
 * 激活会同时改三处状态（旧 active 归档、新 active 生效、审计多两条），
 * 各面板分别刷新必然出现互相矛盾的中间态。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { AppNav } from "@/components/AppNav";
import { BUTTON_CLASS } from "@/components/ui";
import {
  acknowledgeRelease,
  activateRelease,
  getRelease,
  listConfigItems,
  listReleases,
  rollbackRelease,
} from "@/lib/api/config";
import { LAYERS, itemsOfLayer } from "@/lib/config/draft";
import { message } from "@/lib/errors";
import type { ConfigItem, ConfigRelease, ConfigReleaseDetail, ImpactEntry } from "@/types/config";

import { LayerEditor } from "./LayerEditor";
import { ReleasePanel } from "./ReleasePanel";

type LoadState = "loading" | "ready" | "error";

export function ConfigCenter() {
  const [items, setItems] = useState<ConfigItem[]>([]);
  const [role, setRole] = useState("");
  const [active, setActive] = useState<{ release_id: number; version_no: number } | null>(null);
  const [releases, setReleases] = useState<ConfigRelease[]>([]);
  const [detail, setDetail] = useState<ConfigReleaseDetail | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const selectedId = useRef<number | null>(null);

  const reload = useCallback(async () => {
    const [itemsResponse, releaseList] = await Promise.all([listConfigItems(), listReleases()]);
    setItems(itemsResponse.items);
    setRole(itemsResponse.role);
    setActive(itemsResponse.active);
    setReleases(releaseList);
    const fallback =
      releaseList.find((release) => release.id === selectedId.current) ??
      releaseList.find((release) => release.status === "draft") ??
      releaseList[0];
    selectedId.current = fallback?.id ?? null;
    setDetail(fallback === undefined ? null : await getRelease(fallback.id));
  }, []);

  useEffect(() => {
    let alive = true;
    reload()
      .then(() => {
        if (!alive) return;
        setState("ready");
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!alive) return;
        setError(message(caught, "加载配置失败"));
        setState("error");
      });
    return () => {
      alive = false;
    };
  }, [reload]);

  const run = async (fallback: string, task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await task();
      await reload();
    } catch (caught) {
      setError(message(caught, fallback));
    } finally {
      setBusy(false);
    }
  };

  const selectRelease = (id: number) =>
    void run("加载版本详情失败", async () => {
      selectedId.current = id;
      setDetail(await getRelease(id));
    });

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
        <AppNav />
        <span className="text-sm text-slate-500">配置中心</span>
        <span className="text-xs text-slate-400">
          角色 {role} · 生效版本 {active === null ? "—" : "v" + active.version_no}
        </span>
        <button
          type="button"
          className={BUTTON_CLASS + " ml-auto"}
          onClick={() =>
            void run("刷新失败", async () => {
              setInfo(null);
            })
          }
        >
          刷新
        </button>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-4 p-4">
        {state === "loading" && <p className="text-sm text-slate-500">正在加载配置…</p>}

        {state === "error" && (
          <div className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {error ?? "加载失败"}
          </div>
        )}

        {info !== null && (
          <div className="rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800">
            {info}
          </div>
        )}

        {error !== null && state === "ready" && (
          <div className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {state === "ready" && (
          <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
            <div className="flex flex-col gap-4">
              {LAYERS.map((layer) => (
                <LayerEditor
                  key={layer}
                  layer={layer}
                  items={itemsOfLayer(items, layer)}
                  onSaved={async (text) => {
                    setInfo(text);
                    await reload();
                  }}
                />
              ))}
            </div>
            <ReleasePanel
              releases={releases}
              detail={detail}
              busy={busy}
              onSelect={selectRelease}
              onAcknowledge={(entry: ImpactEntry, comment: string) =>
                run("确认失败", async () => {
                  if (detail === null) return;
                  await acknowledgeRelease(detail.id, [entry], comment || undefined);
                  setInfo("已记录确认：" + entry.ref);
                })
              }
              onActivate={(force: boolean, reason: string) =>
                run("激活失败", async () => {
                  if (detail === null) return;
                  await activateRelease(detail.id, { force, reason: reason || undefined });
                  setInfo("版本 v" + detail.version_no + " 已生效");
                })
              }
              onRollback={(reason: string) =>
                run("回滚失败", async () => {
                  if (detail === null) return;
                  await rollbackRelease(detail.id, reason || undefined);
                  setInfo("已回滚到版本 v" + detail.version_no);
                })
              }
            />
          </div>
        )}
      </main>
    </div>
  );
}