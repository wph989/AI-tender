"use client";

import { Suspense, useLayoutEffect, useRef, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";

const HISTORY_KEY = "__aiTenderViewportKey";
const routeOf = (url: URL) => url.pathname + url.search;
let entrySequence = 0;
// 此键只区分本页历史条目；私有 HTTP 部署也要可用，不能依赖安全上下文的 randomUUID。
const newEntryKey = () => `${Date.now()}-${++entrySequence}`;

function RouteScroll({ restore }: { restore: () => void }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const route = pathname + (searchParams.size ? `?${searchParams}` : "");
  useLayoutEffect(restore, [route, restore]);
  return null;
}

/** 根视口跨页面保留；按历史条目记位置，同一 URL 的多次访问也各自恢复。 */
export function AppViewport({ children }: { children: ReactNode }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<() => void>(() => {});
  const restoreAfterCommit = useRef(() => restoreRef.current()).current;

  useLayoutEffect(() => {
    const install = () => {
      const viewport = viewportRef.current!;
      const history = window.history;
      const pushState = history.pushState;
      const replaceState = history.replaceState;
      const positions = new Map<string, number>();
      let key: string = history.state?.[HISTORY_KEY] ?? newEntryKey();
      let currentRoute = routeOf(new URL(window.location.href));
      let pending: number | null = null;
      let cancelRestore = () => {};
      replaceState.call(history, { ...history.state, [HISTORY_KEY]: key }, "");

      const restore = () => {
        if (pending === null) return;
        const target = pending;
        cancelRestore();
        pending = target;
        let animation = 0;
        const stop = () => {
          cancelAnimationFrame(animation);
          resize.disconnect();
          mutations.disconnect();
          pending = null;
        };
        const apply = () => {
          viewport.scrollTop = target;
          if (Math.abs(viewport.scrollTop - target) < 1) stop();
        };
        const schedule = () => {
          cancelAnimationFrame(animation);
          animation = requestAnimationFrame(apply);
        };
        const observeContent = () => {
          resize.disconnect();
          resize.observe(viewport);
          for (const child of viewport.children) resize.observe(child);
          schedule();
        };
        // 返回时列表可能仍是骨架。等内容可容纳目标位置再结束恢复，不写死网络等待时间。
        const resize = new ResizeObserver(schedule);
        const mutations = new MutationObserver(observeContent);
        mutations.observe(viewport, { childList: true, subtree: true });
        cancelRestore = stop;
        observeContent();
      };
      restoreRef.current = restore;

      history.pushState = (data, title, url) => {
        if (pending === null) positions.set(key, viewport.scrollTop);
        cancelRestore();
        key = newEntryKey();
        // 带锚点的目标由 Next/浏览器定位正文，不能用回顶覆盖它。
        pending = new URL(url ?? window.location.href, window.location.href).hash ? null : 0;
        pushState.call(history, { ...data, [HISTORY_KEY]: key }, title, url);
        currentRoute = routeOf(new URL(window.location.href));
      };
      history.replaceState = (data, title, url) => {
        const entryKey: string = history.state?.[HISTORY_KEY] ?? key;
        const nextUrl = new URL(url ?? window.location.href, window.location.href);
        const nextRoute = routeOf(nextUrl);
        // 浏览器可能先提交历史目标、再发 popstate；此时 Next 已开始 replaceState。
        // 从浏览器当前条目取键，不能把离开页的键写进返回目标。
        if (entryKey !== key) {
          if (pending === null) positions.set(key, viewport.scrollTop);
          cancelRestore();
          key = entryKey;
          pending = positions.get(key) ?? 0;
        } else if (nextRoute !== currentRoute) {
          cancelRestore();
          pending = nextUrl.hash ? null : 0;
        }
        // Next.js 内部更新会重建 state；保留自有键及框架字段，不能覆盖路由器状态。
        replaceState.call(history, { ...data, [HISTORY_KEY]: key }, title, url);
        currentRoute = nextRoute;
      };
      const onPopState = (event: PopStateEvent) => {
        const nextKey: string = event.state?.[HISTORY_KEY] ?? newEntryKey();
        const nextRoute = routeOf(new URL(window.location.href));
        // 原生锚点跳转会复制 state；同一条目的 hash 变化交给浏览器处理。
        if (nextKey === key && nextRoute === currentRoute) return;
        if (pending === null) positions.set(key, viewport.scrollTop);
        cancelRestore();
        key = nextKey;
        pending = positions.get(key) ?? 0;
        if (nextRoute === currentRoute) restore();
        currentRoute = nextRoute;
      };
      const onScroll = () => {
        // 恢复过程中的骨架截断、Next 默认滚动不能覆盖历史位置。
        if (pending === null) positions.set(key, viewport.scrollTop);
      };
      const onUserScroll = () => cancelRestore();
      // 捕获阶段先保存离开页；Next 的 popstate 监听可能同步提交目标页并改变视口。
      window.addEventListener("popstate", onPopState, true);
      viewport.addEventListener("scroll", onScroll, { passive: true });
      // 用户主动滚动时立即让出控制，内容缩短或加载失败也不会锁住视口。
      viewport.addEventListener("wheel", onUserScroll, { passive: true });
      viewport.addEventListener("touchstart", onUserScroll, { passive: true });
      viewport.addEventListener("pointerdown", onUserScroll);
      viewport.addEventListener("keydown", onUserScroll);
      return () => {
        cancelRestore();
        history.pushState = pushState;
        history.replaceState = replaceState;
        window.removeEventListener("popstate", onPopState, true);
        viewport.removeEventListener("scroll", onScroll);
        viewport.removeEventListener("wheel", onUserScroll);
        viewport.removeEventListener("touchstart", onUserScroll);
        viewport.removeEventListener("pointerdown", onUserScroll);
        viewport.removeEventListener("keydown", onUserScroll);
        restoreRef.current = () => {};
      };
    };
    // 等 Next 完成 history 的装配及 Strict Mode 的清理重装，避免捕获上一轮已卸载的包装函数。
    let cleanup = () => {};
    const timer = window.setTimeout(() => { cleanup = install(); }, 0);
    return () => {
      window.clearTimeout(timer);
      cleanup();
    };
  }, []);

  return <div ref={viewportRef} className="app-viewport">
    {/* 查询串只影响滚动监听，Suspense 不包裹正文，避免静态页等待水合时重新挂载业务组件。 */}
    <Suspense fallback={null}><RouteScroll restore={restoreAfterCommit} /></Suspense>
    {children}
  </div>;
}
