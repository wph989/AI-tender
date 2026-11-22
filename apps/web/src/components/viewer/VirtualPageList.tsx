"use client";

/**
 * 每页保留轻量占位容器，进入视口附近时才挂载PageView，以限制PDF渲染资源。
 * 占位容器保持可定位：先滚到目标页，再由IntersectionObserver挂载实际页面。
 */

import type { PDFDocumentProxy } from "pdfjs-dist";
import type { RefObject } from "react";
import { useEffect, useMemo, useState } from "react";

import { PageView } from "@/components/viewer/PageView";
import type { PageRegistry } from "@/hooks/usePageRenderer";
import { toPageGeometry } from "@/lib/api/wire";
import { viewportSize } from "@/lib/coords/page";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceIndex, EvidenceItem } from "@/lib/viewer/evidenceIndex";
import type { WirePageMeta } from "@/types/workbench";

/** 页间留白。占位高度必须把它算进去，否则滚动位置会随渲染完成而累积偏移。 */
const PAGE_GAP = 16;

/** 无证据页面的共享空数组：避免每次渲染都造新数组把子组件拖着重渲染 */
const NO_EVIDENCE: readonly EvidenceItem[] = [];

interface Props {
  pdf: PDFDocumentProxy;
  pages: readonly WirePageMeta[];
  scale: number;
  index: EvidenceIndex;
  registry: PageRegistry;
  scrollRef: RefObject<HTMLElement | null>;
  onError: (message: string) => void;
  /** 透传给页面上的角标层：点角标要能反向定位回结果卡（见 06 第 11 节）。 */
  onLocate: (item: EvidenceItem) => void;
}

export function VirtualPageList({
  pdf,
  pages,
  scale,
  index,
  registry,
  scrollRef,
  onError,
  onLocate,
}: Props) {
  const [nearby, setNearby] = useState<ReadonlySet<number>>(() => new Set<number>());
  const setCurrentPage = useViewerStore((state) => state.setCurrentPage);

  // 第一页先挂上：首屏第一眼应该是原文，而不是骨架屏
  useEffect(() => {
    const first = pages[0];
    if (first === undefined) return;
    setNearby((prev) => (prev.has(first.page_no) ? prev : new Set(prev).add(first.page_no)));
  }, [pages]);

  // 预渲染窗口：rootMargin 200% = 视口上下各两屏（见 06 第 7 节）
  useEffect(() => {
    const root = scrollRef.current;
    if (root === null) return;
    const observer = new IntersectionObserver(
      (entries) => {
        setNearby((prev) => {
          const next = new Set(prev);
          let changed = false;
          for (const entry of entries) {
            const raw = (entry.target as HTMLElement).dataset.pageNo;
            if (raw === undefined) continue;
            const pageNo = Number(raw);
            if (entry.isIntersecting) {
              if (!next.has(pageNo)) {
                next.add(pageNo);
                changed = true;
              }
            } else if (next.delete(pageNo)) {
              changed = true;
            }
          }
          // 没有变化就返回原对象：滚动时 observer 会持续回调，否则每次都要重渲染整棵树
          return changed ? next : prev;
        });
      },
      { root, rootMargin: "200% 0px", threshold: 0 },
    );
    for (const element of root.querySelectorAll("[data-page-no]")) observer.observe(element);
    return () => observer.disconnect();
  }, [pages, scrollRef]);

  // 当前页码：取「越过容器上三分之一探测线」的最后一页。
  // 不用 IntersectionObserver 统计可见比例：页高差异大（横版页）时比例阈值会误判。
  useEffect(() => {
    const root = scrollRef.current;
    if (root === null) return;
    let frame = 0;
    const probe = () => {
      frame = 0;
      const line = root.getBoundingClientRect().top + root.clientHeight * 0.34;
      let current = pages[0]?.page_no ?? 1;
      for (const element of root.querySelectorAll<HTMLElement>("[data-page-no]")) {
        // 占位容器与页码同序，越过探测线的第一个元素之后就不用再看了
        if (element.getBoundingClientRect().top > line) break;
        const raw = element.dataset.pageNo;
        if (raw !== undefined) current = Number(raw);
      }
      setCurrentPage(current);
    };
    const onScroll = () => {
      if (frame === 0) frame = requestAnimationFrame(probe);
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    probe();
    return () => {
      root.removeEventListener("scroll", onScroll);
      if (frame !== 0) cancelAnimationFrame(frame);
    };
  }, [pages, scrollRef, setCurrentPage]);

  const slots = useMemo(
    () =>
      pages.map((page) => {
        const size = viewportSize(toPageGeometry(page));
        return { page, width: size.width * scale, height: size.height * scale };
      }),
    [pages, scale],
  );

  return (
    <div className="flex w-full flex-col">
      {slots.map(({ page, width, height }) => (
        <div
          key={page.page_no}
          data-page-no={page.page_no}
          className="flex w-full justify-center"
          style={{ height: height + PAGE_GAP }}
        >
          {nearby.has(page.page_no) ? (
            <PageView
              pdf={pdf}
              page={page}
              scale={scale}
              items={index.byPage.get(page.page_no) ?? NO_EVIDENCE}
              registry={registry}
              onError={onError}
              onLocate={onLocate}
            />
          ) : (
            <div className="rounded-sm bg-white/70 ring-1 ring-slate-200" style={{ width, height }} />
          )}
        </div>
      ))}
    </div>
  );
}
