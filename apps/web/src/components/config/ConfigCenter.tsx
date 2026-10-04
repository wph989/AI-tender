"use client";

/**
 * 配置中心页容器（设计文档 08 第 2、5、6 节）。
 *
 * 任何写操作后统一重取"配置项 + 版本列表 + 当前选中版本详情"：
 * 激活会同时改三处状态（旧 active 归档、新 active 生效、审计多两条），
 * 各面板分别刷新必然出现互相矛盾的中间态。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { PageShell } from "@/components/PageShell";
import { BUTTON_CLASS, DATA_CLASS } from "@/components/ui";
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
  const [section, setSection] = useState("L1");
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

  const retry = () => {
    setState("loading");
    setError(null);
    void reload()
      .then(() => setState("ready"))
      .catch((caught: unknown) => {
        setError(message(caught, "加载配置失败"));
        setState("error");
      });
  };

  return (
    <PageShell
      breadcrumb={[<span>设置</span>, <span className="text-slate-600">配置中心</span>]}
      eyebrow="设置 · 配置"
      title="配置中心"
      description="管理运行、解析与抽取规则，查看每一次配置发布的影响。"
      actions={
        <>
          <span className="text-[13px] text-slate-500">
            角色 <span className={DATA_CLASS + " text-slate-700"}>{role === "" ? "—" : role}</span>
          </span>
          <span className="text-[13px] text-slate-500">
            生效版本{" "}
            <span className={DATA_CLASS + " text-slate-700"}>
              {active === null ? "—" : "v" + active.version_no}
            </span>
          </span>
          <button
            type="button"
            className={BUTTON_CLASS}
            disabled={busy}
            onClick={() =>
              void run("刷新失败", async () => {
                setInfo(null);
              })
            }
          >
            刷新
          </button>
        </>
      }
    >
      {state === "loading" && <p className="text-[14px] text-slate-500">正在加载配置…</p>}

      {state === "error" && (
        <div className="border border-rose-200 bg-rose-50 px-4 py-3 text-[14px] text-rose-700">
          <p>{error ?? "加载失败"}</p>
          <p className="mt-1 text-[13px] text-rose-600">
            暂时无法获取配置，请确认服务可用后重试。
          </p>
          <button type="button" className={BUTTON_CLASS + " mt-2"} onClick={retry}>
            重试
          </button>
        </div>
      )}

      {info !== null && (
        <div className="border border-sky-200 bg-sky-50 px-4 py-3 text-[14px] text-sky-800">
          {info}
        </div>
      )}

      {error !== null && state === "ready" && (
        <div className="border border-rose-200 bg-rose-50 px-4 py-3 text-[14px] text-rose-700">
          {error}
        </div>
      )}

      {state === "ready" && (
        <div className="settings-layout">
          <nav className="settings-nav" aria-label="配置分类">
            {[
              { key: "L1", label: "运行参数", hint: "并发与超时 · 立即生效" },
              { key: "L2", label: "解析配置", hint: "文档解析 · 发布后生效" },
              { key: "L3", label: "抽取配置", hint: "信息抽取 · 发布后生效" },
              { key: "releases", label: "版本与发布", hint: "变更确认、发布与回滚" },
            ].map((item) => <button key={item.key} type="button" aria-pressed={section === item.key} onClick={() => setSection(item.key)}>
              <span className="nav-step">{item.key === "releases" ? "↗" : item.key}</span>
              <span><strong>{item.label}</strong><small>{item.hint}</small></span>
            </button>)}
            <p className="settings-help">解析与抽取配置先保存为草稿。确认影响并通过检查后，在「版本与发布」中生效。</p>
          </nav>
          <div className="settings-main">
            {LAYERS.map((layer) => <div key={layer} hidden={section !== layer}>
              <LayerEditor layer={layer} items={itemsOfLayer(items, layer)} onSaved={async (text) => { setInfo(text); await reload(); }} />
            </div>)}
            <div hidden={section !== "releases"}>
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
          </div>
        </div>
      )}
    </PageShell>
  );
}
