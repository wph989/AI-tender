"use client";

/**
 * 单页视图：占位尺寸 + canvas 位图 + 高亮层。
 *
 * 两个「为什么」：
 *  1. width/height 由后端页面几何 × 当前 scale 算出，**在 canvas 画出来之前就定死**：
 *     占位高度与真实渲染高度逐像素一致，页面渲染完成的瞬间才不会跳一下（见 06 第 7 节）。
 *  2. scale 变化时先清空本地 viewport：旧尺寸下画出的高亮框会整体偏移，
 *     宁可短暂不画，也不能画一个位置错的框（见 06 第 6 节）。
 */

import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useRef, useState } from "react";

import { AnnotationLayer } from "@/components/viewer/AnnotationLayer";
import { CanvasLayer } from "@/components/viewer/CanvasLayer";
import { EvidenceLayer } from "@/components/viewer/EvidenceLayer";
import type { PageRegistry } from "@/hooks/usePageRenderer";
import { assertViewportMatches, toPageGeometry } from "@/lib/api/wire";
import type { Size } from "@/lib/coords/bbox";
import { viewportSize } from "@/lib/coords/page";
import { useViewerStore } from "@/lib/store/viewerStore";
import type { EvidenceItem } from "@/lib/viewer/evidenceIndex";
import type { WirePageMeta } from "@/types/workbench";

interface Props {
  pdf: PDFDocumentProxy;
  page: WirePageMeta;
  scale: number;
  items: readonly EvidenceItem[];
  registry: PageRegistry;
  onError: (message: string) => void;
  /** 点原文页上的角标 → 反向定位到对应结果卡（见 docs/设计/06 第 11 节）。 */
  onLocate: (item: EvidenceItem) => void;
}

export function PageView({ pdf, page, scale, items, registry, onError, onLocate }: Props) {
  const pageNo = page.page_no;
  const rootRef = useRef<HTMLDivElement | null>(null);
  const evidenceRootRef = useRef<HTMLDivElement | null>(null);
  const [viewport, setViewport] = useState<Size | null>(null);

  const expected = viewportSize(toPageGeometry(page));
  const width = expected.width * scale;
  const height = expected.height * scale;

  const activeEvidence = useViewerStore((state) => state.activeEvidence);
  const pulseKey = useViewerStore((state) => state.pulseKey);
  const setNotice = useViewerStore((state) => state.setNotice);

  // 注册/注销：定位时序靠登记表拿到「此刻挂载的 DOM」，卸载即失效（见 usePageRenderer 的说明）
  useEffect(() => {
    const root = rootRef.current;
    if (root === null) return;
    registry.mount(pageNo, root, evidenceRootRef.current);
    return () => registry.unmount(pageNo);
  }, [pageNo, registry]);

  // 缩放后旧视口尺寸作废，等新的一帧画完由 handleRendered 写回
  useEffect(() => {
    setViewport(null);
  }, [scale]);

  const handleRendered = useCallback(
    (size: Size) => {
      // 渲染基座与解析基座必须吻合（见 05 第 3.2 节）：不吻合说明两边几何口径已错位，
      // 此时画出来的高亮不可信，必须让用户看见，而不是静默画一个漂移的框
      const mismatch = assertViewportMatches(
        { width: expected.width * scale, height: expected.height * scale },
        size,
      );
      if (mismatch !== null) setNotice(mismatch);
      setViewport(size);
      registry.markRendered(pageNo, size);
    },
    [expected.height, expected.width, pageNo, registry, scale, setNotice],
  );


  return (
    <div
      ref={rootRef}
      className="relative bg-white shadow-sm ring-1 ring-slate-300"
      style={{ width, height }}
    >
      <CanvasLayer pdf={pdf} pageNo={pageNo} scale={scale} onRendered={handleRendered} onError={onError} />
      <div ref={evidenceRootRef} className="absolute inset-0">
        <EvidenceLayer
          pageNo={pageNo}
          activeEvidence={activeEvidence}
          pulseKey={pulseKey}
          viewport={viewport}
        />
        {/* 角标层压在证据框之上：它要可点，也必须盖住底框的描边 */}
        <AnnotationLayer
          pageNo={pageNo}
          items={items}
          activeEvidence={activeEvidence}
          viewport={viewport}
          onLocate={onLocate}
        />
      </div>
    </div>
  );
}
