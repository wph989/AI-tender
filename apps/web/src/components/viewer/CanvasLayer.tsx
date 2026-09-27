"use client";

/**
 * 用 pdf.js 把一页画到 canvas 上。
 *
 * 两个容易踩的点：
 *  1. `rotation` 必须显式传 `page.rotate`。不传的话 pdf.js 用的是页面自带旋转，
 *     看似正确，但只要将来支持「用户手动旋转视图」，两条路径就会分叉——
 *     显式传等于把「视口方向 = 视觉方向」这件事写在代码里（见 docs/设计/03 第 3.4 节）。
 *  2. 卸载时必须 `renderTask.cancel()` + `page.cleanup()`。不取消的话缩放时会留下
 *     一次「幽灵渲染」，它在新内容之后完成、把旧尺寸的位图盖回去（见 docs/设计/06 第 7 节）。
 */

import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import { useEffect, useRef } from "react";

import type { Size } from "@/lib/coords/bbox";

interface Props {
  pdf: PDFDocumentProxy;
  pageNo: number;
  scale: number;
  onRendered: (viewport: Size) => void;
  onError: (message: string) => void;
}

export function CanvasLayer({ pdf, pageNo, scale, onRendered, onError }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    let task: RenderTask | null = null;
    let page: PDFPageProxy | null = null;

    void (async () => {
      try {
        page = await pdf.getPage(pageNo);
        if (cancelled) return;
        const viewport = page.getViewport({ scale, rotation: page.rotate });
        const canvas = canvasRef.current;
        if (!canvas) return;

        // 高分屏：backing store 放大 ratio 倍，再用 render 的 transform 抵消，
        // 这样 CSS 尺寸仍是 viewport 尺寸——高亮层按 CSS 像素算，不能跟着放大。
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;

        const context = canvas.getContext("2d");
        if (!context) return;
        task = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        await task.promise;
        if (cancelled) return;
        onRendered({ width: viewport.width, height: viewport.height });
      } catch (error) {
        if (cancelled) return;
        onError(error instanceof Error ? error.message : `第 ${pageNo} 页渲染失败`);
      }
    })();

    return () => {
      cancelled = true;
      task?.cancel();
      page?.cleanup();
    };
  }, [onError, onRendered, pageNo, pdf, scale]);

  return <canvas ref={canvasRef} className="block" />;
}