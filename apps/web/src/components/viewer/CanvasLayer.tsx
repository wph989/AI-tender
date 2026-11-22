"use client";

/**
 * 用 pdf.js 把一页画到 canvas 上。
 *
 * 画布和页尺寸统一使用PDF的旋转信息，保证证据坐标与渲染方向一致。
 * 卸载时取消渲染并清理页面，避免缩放前的旧任务覆盖新画布。
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
