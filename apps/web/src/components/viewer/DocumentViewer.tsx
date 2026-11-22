"use client";

/**
 * 原文视图：滚动容器 + 适应宽度测量 + 虚拟页列表。
 *
 * 缩放基准取「适应宽度 × 用户倍率」，且**所有页共用一个 scale**：
 * 横版页（带 /Rotate 的扫描件）在自己的页框里居中留白，而不是被单独放大——
 * 否则跨页时字号忽大忽小，用户会怀疑解析坐标有偏差（见 docs/设计/06-前端展示与定位.md）。
 */

import type { PDFDocumentProxy } from "pdfjs-dist";
import { useEffect, useMemo, useRef, useState } from "react";

import { VirtualPageList } from "@/components/viewer/VirtualPageList";
import type { PageRegistry } from "@/hooks/usePageRenderer";
import { toPageGeometry } from "@/lib/api/wire";
import { viewportSize } from "@/lib/coords/page";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceIndex, EvidenceItem } from "@/lib/viewer/evidenceIndex";
import type { WirePageMeta } from "@/types/workbench";

interface Props {
  pdf: PDFDocumentProxy;
  pages: readonly WirePageMeta[];
  index: EvidenceIndex;
  registry: PageRegistry;
  onError: (message: string) => void;
  /** 原文页角标 → 结果卡的反向定位（见 docs/设计/06-前端展示与定位.md）。 */
  onLocate: (item: EvidenceItem) => void;
}

export function DocumentViewer({ pdf, pages, index, registry, onError, onLocate }: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const measureRef = useRef<HTMLDivElement | null>(null);
  const [contentWidth, setContentWidth] = useState(0);

  const zoom = useViewerStore((state) => state.zoom);
  const jumpRequest = useViewerStore((state) => state.jumpRequest);

  // 基准宽度只取第一页的视觉宽度：所有页共用一个 scale，横版页因此会留白（见文件头说明）
  const baseWidth = useMemo(() => {
    const first = pages[0];
    return first === undefined ? 0 : viewportSize(toPageGeometry(first)).width;
  }, [pages]);

  const fitScale = contentWidth > 0 && baseWidth > 0 ? contentWidth / baseWidth : 0;
  const scale = fitScale * zoom;

  useEffect(() => {
    const element = measureRef.current;
    if (element === null) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry !== undefined) setContentWidth(entry.contentRect.width);
    });
    observer.observe(element);
    setContentWidth(element.clientWidth);
    return () => observer.disconnect();
  }, []);

  // 缩放/容器变化后 canvas 尺寸失效：登记表里的旧视口尺寸必须作废，
  // 否则定位会拿旧尺寸算矩形，表现为「高亮比例对但整体偏移」（见 06 第 6 节）
  useEffect(() => {
    registry.invalidate();
  }, [registry, scale]);

  // 页码跳转：占位容器常驻，所以不依赖目标页是否已挂载（见 06 第 3 节）
  useEffect(() => {
    const container = scrollRef.current;
    if (container === null || jumpRequest === null) return;
    const slot = container.querySelector<HTMLElement>(`[data-page-no="${jumpRequest.pageNo}"]`);
    if (slot === null) return;
    // 直接算 scrollTop，避免 scrollIntoView 连带滚动祖先与窗口
    container.scrollTo({ top: Math.max(0, slot.offsetTop - 8), behavior: "auto" });
  }, [jumpRequest]);

  return (
    <div
      ref={scrollRef}
      data-scroll-root
      className="viewer-surface relative h-full overflow-auto px-4 py-5 md:px-7"
    >
      <div ref={measureRef} className="mx-auto w-full max-w-[1240px]">
        {fitScale > 0 ? (
          <VirtualPageList
            pdf={pdf}
            pages={pages}
            scale={scale}
            index={index}
            registry={registry}
            scrollRef={scrollRef}
            onError={onError}
            onLocate={onLocate}
          />
        ) : (
          <div className="py-24 text-center text-[14px] text-slate-500">正在计算页面尺寸…</div>
        )}
      </div>
    </div>
  );
}
