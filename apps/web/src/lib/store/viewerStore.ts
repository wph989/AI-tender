/**
 * 原文视图的 UI 状态。
 *
 * 为什么用 Zustand 且只放这些：当前高亮、缩放、提示语、当前页码都是「与数据无关的视图状态」，
 * 放 React 上下文会在页面级滚动时反复重建，放 Redux 又不值当（见 docs/工程/10 第 2 节）。
 *
 * 关键在 `activeEvidence` **必须进状态**而不是画完即忘：
 * 缩放、容器 resize、页面卸载重挂之后都要靠它自动重算高亮矩形（见 docs/设计/06 第 6 节）。
 *
 * `jumpRequest` 用「请求 + token」而不是暴露滚动函数：Toolbar 与原文视图分属两棵子树，
 * 用状态传命令可以避免把滚动容器的 ref 一路透传（见 docs/工程/11 第 6 节的组件通信取舍）。
 */

import { create } from "zustand";

import type { Bbox } from "@/lib/coords/bbox";

export interface ActiveEvidence {
  extractionId: number;
  anchor: string;
  pageNo: number;
  /** null = 只有页级定位（bbox 缺失或非法），此时高亮整页边框（见 docs/设计/06 第 5 节）。 */
  bbox: Bbox | null;
  label: string;
}

export interface JumpRequest {
  pageNo: number;
  /** 自增序号：连续跳到同一页也要重新执行一次滚动 */
  token: number;
}

interface ViewerState {
  /** 用户缩放倍率，最终 scale = 适应宽度 × 倍率。 */
  zoom: number;
  /** 原文视图当前停留的页码（由滚动位置反推），Toolbar 只读。 */
  currentPage: number;
  activeEvidence: ActiveEvidence | null;
  /** 自增计数：同一个证据被连续点击时也要重新闪一次，否则用户以为没响应。 */
  pulseKey: number;
  notice: string | null;
  jumpRequest: JumpRequest | null;
  setZoom: (zoom: number) => void;
  setCurrentPage: (pageNo: number) => void;
  setActiveEvidence: (evidence: ActiveEvidence | null) => void;
  pulse: () => void;
  setNotice: (notice: string | null) => void;
  requestJump: (pageNo: number) => void;
}

export const useViewerStore = create<ViewerState>((set) => ({
  zoom: 1,
  currentPage: 1,
  activeEvidence: null,
  pulseKey: 0,
  notice: null,
  jumpRequest: null,
  setZoom: (zoom) => set({ zoom: Math.min(4, Math.max(0.25, zoom)) }),
  // 页码一致时返回原状态对象：zustand 用引用相等判断是否需要通知，能省掉滚动过程中的无谓重渲染
  setCurrentPage: (pageNo) => set((state) => (state.currentPage === pageNo ? state : { currentPage: pageNo })),
  setActiveEvidence: (activeEvidence) => set({ activeEvidence }),
  pulse: () => set((state) => ({ pulseKey: state.pulseKey + 1 })),
  setNotice: (notice) => set({ notice }),
  requestJump: (pageNo) =>
    set((state) => ({
      jumpRequest: { pageNo, token: (state.jumpRequest?.token ?? 0) + 1 },
    })),
}));