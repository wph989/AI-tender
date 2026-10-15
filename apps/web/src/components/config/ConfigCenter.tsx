"use client";
import { Button, Tabs } from "antd";
import { useFeedback } from "@/hooks/useFeedback";

/**
 * 配置中心页容器（设计文档 08 第 2、5、6 节）。
 *
 * 任何写操作后统一重取"配置项 + 版本列表 + 当前选中版本详情"：
 * 激活会同时改三处状态（旧 active 归档、新 active 生效、审计多两条），
 * 各面板分别刷新必然出现互相矛盾的中间态。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { PageShell } from "@/components/PageShell";
import { DATA_CLASS } from "@/components/ui";
import {
  acknowledgeRelease,
  activateRelease,
  getRelease,
  listConfigItems,
  listReleases,
  rollbackRelease,
} from "@/lib/api/config";
import { LAYERS, isModelConfig, itemsOfLayer } from "@/lib/config/draft";
import { message } from "@/lib/errors";
import type {
  ConfigItem,
  ConfigRelease,
  ConfigReleaseDetail,
  ImpactEntry,
} from "@/types/config";

import { LayerEditor } from "./LayerEditor";
import { ReleasePanel } from "./ReleasePanel";

type LoadState = "loading" | "ready" | "error";

export function ConfigCenter() {
  return (
    <PageShell
      breadcrumb={[<span>设置</span>, <span>配置中心</span>]}
      eyebrow="设置 · 配置"
      title="配置中心"
      description="管理文件转换与解析规则。模型与分析预算请到模型管理调整。"
    >
      <ConfigWorkspace scope="system" />
    </PageShell>
  );
}

export function ConfigWorkspace({ scope }: { scope: "system" | "models" }) {
  const [section, setSection] = useState("L1");
  const [items, setItems] = useState<ConfigItem[]>([]);
  const [role, setRole] = useState("");
  const [active, setActive] = useState<{
    release_id: number;
    version_no: number;
  } | null>(null);
  const [releases, setReleases] = useState<ConfigRelease[]>([]);
  const [detail, setDetail] = useState<ConfigReleaseDetail | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useFeedback(error, info);
  const selectedId = useRef<number | null>(null);
  const loadSequence = useRef(0);

  const reload = useCallback(async () => {
    const sequence = ++loadSequence.current;
    const [itemsResponse, releaseList] = await Promise.all([
      listConfigItems(),
      listReleases(),
    ]);
    if (sequence !== loadSequence.current) return;
    setItems(itemsResponse.items.filter(
      (item) => isModelConfig(item.key) === (scope === "models"),
    ));
    setRole(itemsResponse.role);
    setActive(itemsResponse.active);
    setReleases(releaseList);
    const fallback =
      releaseList.find((release) => release.id === selectedId.current) ??
      releaseList.find((release) => release.status === "draft") ??
      releaseList[0];
    selectedId.current = fallback?.id ?? null;
    const nextDetail = fallback === undefined ? null : await getRelease(fallback.id);
    if (sequence === loadSequence.current && selectedId.current === (fallback?.id ?? null)) setDetail(nextDetail);
  }, [scope]);

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
      await reload().catch(() => setError("操作已完成，刷新配置失败，请点击刷新。"));
    } catch (caught) {
      setError(message(caught, fallback));
    } finally {
      setBusy(false);
    }
  };

  const selectRelease = (id: number) => {
    selectedId.current = id;
    setDetail(null);
    setBusy(true);
    setError(null);
    // 详情读取与发布分开，快速切换版本时只接纳最后一次请求。
    void getRelease(id)
      .then((next) => {
        if (selectedId.current === id) setDetail(next);
      })
      .catch((caught) => {
        if (selectedId.current === id)
          setError(message(caught, "加载版本详情失败"));
      })
      .finally(() => {
        if (selectedId.current === id) setBusy(false);
      });
  };

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
    <>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <span className="text-[13px] text-slate-500">
          角色{" "}
          <span className={DATA_CLASS + " text-slate-700"}>
            {role === "" ? "—" : role}
          </span>
        </span>
        <span className="text-[13px] text-slate-500">
          生效版本{" "}
          <span className={DATA_CLASS + " text-slate-700"}>
            {active === null ? "—" : "v" + active.version_no}
          </span>
        </span>
        <Button
          htmlType="button"
          disabled={busy}
          onClick={() => state === "ready"
            ? void run("刷新失败", async () => { setInfo(null); })
            : retry()}
        >
          刷新
        </Button>
      </div>
      {scope === "models" && (
        <p className="mb-4 text-sm text-slate-500">
          分析预算用于新建与补跑的模块；模型自身的输出上限仍同时生效。
          配置版本与配置中心共用，发布和回滚会作用于整个版本。
        </p>
      )}
      {state === "loading" && (
        <p className="text-[14px] text-slate-500">正在加载配置…</p>
      )}

      {state === "error" && (
        <div className="border border-rose-200 bg-rose-50 px-4 py-3 text-[14px] text-rose-700">
          <p>{error ?? "加载失败"}</p>
          <p className="mt-1 text-[13px] text-rose-600">
            暂时无法获取配置，请确认服务可用后重试。
          </p>
          <Button htmlType="button" className={" mt-2"} onClick={retry}>
            重试
          </Button>
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
        <Tabs
          activeKey={section === "releases" || items.some((item) => item.layer === section)
            ? section : items[0]?.layer ?? "releases"}
          onChange={setSection}
          destroyOnHidden={false}
          items={[
            ...LAYERS.filter((layer) => itemsOfLayer(items, layer).length > 0).map((layer) => ({
              key: layer,
              label:
                layer === "L1"
                  ? scope === "models" ? "分析运行预算" : "运行参数"
                  : layer === "L2"
                    ? scope === "models" ? "模型辅助解析" : "解析配置"
                    : "解析配置",
              forceRender: true,
              children: (
                <LayerEditor
                  layer={layer}
                  items={itemsOfLayer(items, layer)}
                  onSaved={async (text) => {
                    setInfo(text);
                    await reload();
                    if (layer !== "L1") setSection("releases");
                  }}
                />
              ),
            })),
            {
              key: "releases",
              label: "版本与发布",
              forceRender: true,
              children: (
                <ReleasePanel
                  releases={releases}
                  error={error}
                  onRetry={() =>
                    selectedId.current !== null &&
                    selectRelease(selectedId.current)
                  }
                  detail={detail}
                  busy={busy}
                  onSelect={selectRelease}
                  onAcknowledge={(entry: ImpactEntry, comment: string) =>
                    run("确认失败", async () => {
                      if (detail === null) return;
                      await acknowledgeRelease(
                        detail.id,
                        [entry],
                        comment || undefined,
                      );
                      setInfo("已记录确认：" + entry.ref);
                    })
                  }
                  onActivate={(force: boolean, reason: string) =>
                    run("激活失败", async () => {
                      if (detail === null) return;
                      await activateRelease(detail.id, {
                        force,
                        reason: reason || undefined,
                      });
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
              ),
            },
          ]}
        />
      )}
    </>
  );
}
