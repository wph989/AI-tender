/**
 * 取数入口：**调用方唯一需要改的地方就是这里**。
 *
 * 现在从 public/samples 的静态 JSON 取数（阶段 1 的验收要求是「先用假结果数据跑通点击定位」，
 * 见 docs/工程/07），接口落地后把两个 fetch 换成 /api/v1/... 即可，组件一行不用动。
 *
 * 为什么连 PDF 也走静态路径：原文预览的唯一数据源是版本文件（将来是带 Range 的
 * GET /versions/{vid}/file，见 docs/设计/05 第 1 节）。这一刀刻意让前端先习惯
 * 「PDF 是外部资源、按 URL 流式取」这件事，而不是把 base64 塞进 JSON 里。
 */

import type { WireBlock, WireExtraction, WirePageMeta } from "@/types/workbench";

export interface WorkbenchData {
  pdfUrl: string;
  pages: WirePageMeta[];
  blocksByPage: Record<string, WireBlock[]>;
  extractions: WireExtraction[];
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`取数失败：${url} 返回 ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function loadSampleWorkbench(): Promise<WorkbenchData> {
  const [document, extractions] = await Promise.all([
    getJson<{ pages: WirePageMeta[]; blocks_by_page: Record<string, WireBlock[]> }>(
      "/samples/sample-document.json",
    ),
    getJson<{ items: WireExtraction[] }>("/samples/sample-extractions.json"),
  ]);
  return {
    pdfUrl: "/samples/sample-tender.pdf",
    pages: document.pages,
    blocksByPage: document.blocks_by_page,
    extractions: extractions.items,
  };
}