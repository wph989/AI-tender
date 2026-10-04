/**
 * 点击结果 → 定位并高亮原文。这是整个前端最关键的时序（见 docs/设计/06 第 5 节）。
 *
 * 六步的顺序不可调换，每一步都对应一个真实的失败模式：
 *   ① 必须先确保目标页已渲染完成，否则「跳过去了但没高亮」
 *   ② 必须先做页面级滚动让页面挂载，再画 overlay，否则 overlay 挂在未挂载的 DOM 上
 *   ③ 等一帧让布局稳定，否则量到的是滚动前的矩形
 *   ④ 写入状态而不是直接操作 DOM，缩放/resize 时才能自动重算矩形
 *   ⑤ 页内精确滚动用几何计算（见 lib/viewer/scroll.ts），不能用 scrollIntoView(高亮元素)
 *   ⑥ 自增 pulseKey 触发闪烁，否则连续点同一条会像没反应
 */

"use client";

import { useCallback, useEffect, useRef } from "react";

import type { MountedPage, PageRegistry } from "@/hooks/usePageRenderer";
import type { ActiveEvidence } from "@/lib/store/viewerStore";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { Bbox } from "@/lib/coords/bbox";
import { centerBboxScrollTop } from "@/lib/viewer/scroll";

function nextFrame(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}

/** 小屏切回原文时，ResizeObserver 重新测宽后才会恢复虚拟页占位，不能提前滚动。 */
async function waitForPageSlot(pageNo: number, isCurrent: () => boolean): Promise<HTMLElement | null> {
  const deadline = performance.now() + 4000;
  while (isCurrent() && performance.now() < deadline) {
    const slot = document.querySelector<HTMLElement>(`[data-page-no="${pageNo}"]`);
    if (slot && slot.getBoundingClientRect().height > 0) return slot;
    await nextFrame();
  }
  return null;
}

/** ⑤ 页内精确滚动：把高亮块垂直居中到滚动容器 */
function scrollBboxToCenter(page: MountedPage, bbox: Bbox): void {
  const container = page.root.closest<HTMLElement>("[data-scroll-root]");
  const viewport = page.viewport;
  // 只有页级定位或容器结构变了（理论上不会）时静默跳过：页面已经滚到位，不需要再报错
  if (container === null || viewport === null) return;

  const containerRect = container.getBoundingClientRect();
  const pageRect = page.root.getBoundingClientRect();
  const top = centerBboxScrollTop(
    {
      containerTop: containerRect.top,
      scrollTop: container.scrollTop,
      clientHeight: container.clientHeight,
      pageTop: pageRect.top,
    },
    viewport,
    bbox,
  );
  container.scrollTo({ top, behavior: "smooth" });
}

export function useLocate(registry: PageRegistry) {
  // 请求序号：快速连点不同结果时丢弃过期请求，避免最后停在中间某一页
  const sequence = useRef(0);
  // 切换文件时终止旧文档的等待，防止稍后完成的定位覆盖新文件状态。
  useEffect(() => () => { sequence.current += 1; }, []);

  const setActiveEvidence = useViewerStore((state) => state.setActiveEvidence);
  const setNotice = useViewerStore((state) => state.setNotice);
  const pulse = useViewerStore((state) => state.pulse);

  const locate = useCallback(
    async (target: ActiveEvidence): Promise<void> => {
      const token = (sequence.current += 1);

      try {
        // ① 目标页没渲染就先把它滚进视口（虚拟滚动靠 IntersectionObserver 触发挂载），再等它画完
        let page = registry.rendered(target.pageNo);
        if (!page || page.root.getBoundingClientRect().height === 0) {
          const slot = await waitForPageSlot(target.pageNo, () => token === sequence.current);
          if (token !== sequence.current) return;
          if (slot) {
            slot.scrollIntoView({ block: "center" });
            page = registry.rendered(target.pageNo) ?? await registry.waitFor(target.pageNo);
          } else {
            page = null;
          }
        }
        if (token !== sequence.current) return;

        if (!page) {
          // 渲染超时：降级为仅提示，不阻断用户继续核对别的字段
          setNotice(`第 ${target.pageNo} 页渲染超时，已无法定位到该处`);
          return;
        }

        // ② 页面级滚动
        page.root.scrollIntoView({ block: "center", behavior: "auto" });
        // ③ 等布局稳定
        await nextFrame();
        if (token !== sequence.current) return;

        // ④ 高亮进状态
        setActiveEvidence(target);

        if (target.bbox === null) {
          // 只有页级定位：不做矩形高亮，整页边框闪一下并说明原因
          setNotice(`「${target.label}」仅有页级定位，未提供块坐标`);
        } else {
          // ⑤ 页内精确滚动
          scrollBboxToCenter(page, target.bbox);
        }
        // ⑥ 闪烁
        pulse();
      } catch (error) {
        if (token !== sequence.current) return;
        setNotice(error instanceof Error ? error.message : "定位失败");
      }
    },
    [pulse, registry, setActiveEvidence, setNotice],
  );

  return { locate };
}
