/**
 * 原文视图的 UI 状态。
 *
 * Zustand集中管理高亮、缩放、提示和页码，供工具栏与原文视图共享。
 * activeEvidence保留归一化坐标，缩放、窗口变化或重新挂载时据此重算高亮矩形。
 * jumpRequest的递增token让重复选择同一位置也触发滚动。
 */

import { create } from "zustand";

import type { Bbox } from "@/lib/coords/bbox";

export interface ActiveEvidence {
  evidenceId: number;
  anchor: string;
  pageNo: number;
  /** null = 只有页级定位（bbox 缺失或非法），此时高亮整页边框（见 docs/设计/06-前端展示与定位.md）。 */
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
