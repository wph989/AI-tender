"use client";

/**
 * PDF 基座加载器（见 docs/设计/06-前端展示与定位.md）。
 *
 * 为什么用动态 import：pdfjs 在模块求值阶段就会碰浏览器全局对象（DOMMatrix / Worker 等），
 * 静态 import 会被 SSR 一并求值而报错。这里保证只在浏览器、只在 effect 里加载。
 *
 * worker 与 cMaps 走 public/pdfjs 下的固定 URL（由 scripts/copy-pdfjs-assets.mjs 生成）：
 * 与打包器无关，也避免 cMaps 缺失导致 CID 字体的中文整页空白。
 *
 * 为什么用 legacy 构建：pdfjs 6.x 的现代构建直接用 `Map.prototype.getOrInsertComputed`，
 * 这是刚进 V8 的新方法——实测 Chrome 142 直接抛 "not a function"，整份文档一页都渲染不出来。
 * legacy 构建自带该方法的 polyfill，且这正是官方面向旧浏览器的入口；
 * 内网桌面的浏览器版本不可控，用 legacy 是唯一稳妥的选择（现代构建的额外收益只是包体略小）。
 */

import type { PDFDocumentProxy } from "pdfjs-dist";

/** Worker地址是全局选项，多个PDF共用一次初始化。 */
let workerConfigured = false;

export async function loadPdfDocument(url: string): Promise<PDFDocumentProxy> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");

  if (!workerConfigured) {
    pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
    workerConfigured = true;
  }

  return pdfjs.getDocument({
    url,
    cMapUrl: "/pdfjs/cmaps/",
    cMapPacked: true,
    standardFontDataUrl: "/pdfjs/standard_fonts/",
    wasmUrl: "/pdfjs/wasm/",
    iccUrl: "/pdfjs/iccs/",
  }).promise;
}
/**
 * 释放文档：pdfjs v6 的销毁入口挂在 loadingTask 上（PDFDocumentProxy 本身没有 destroy），
 * 把这个 API 细节留在本模块，调用方只需要「拿到文档 / 放掉文档」两个动作。
 */
export function destroyPdfDocument(document: PDFDocumentProxy): void {
  void document.loadingTask.destroy();
}
