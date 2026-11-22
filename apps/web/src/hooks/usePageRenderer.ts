/**
 * 已渲染页面的登记表：定位时序的「等待」就落在这里。
 *
 * 为什么需要它：虚拟滚动下目标页通常还没挂载（见 docs/设计/06-前端展示与定位.md）。
 * 定位必须能「等到那一页真的画出来」再往下走，否则会出现「跳过去了但没高亮」——
 * 这类失败只在跨多页点击时复现，靠手测很容易漏。
 *
 * 为什么用登记表而不是 Promise 缓存：页面会被卸载重挂（滚动出视口、缩放重绘），
 * Promise 一旦被缓存就会在页面卸载后仍返回一个指向已销毁 DOM 的对象；
 * 登记表以「当前挂载的 DOM」为准，卸载即失效，调用方重新等待。
 */

"use client";

import { useRef } from "react";

import type { Size } from "@/lib/coords/bbox";

export interface MountedPage {
  pageNo: number;
  /** 整页容器：页面级滚动用它 */
  root: HTMLElement;
  /** 高亮层容器：页内精确滚动用它 */
  evidenceRoot: HTMLElement | null;
  /** 渲染完成后的视口尺寸（CSS px）；null = 这一页还没画出来 */
  viewport: Size | null;
}

type Waiter = (page: MountedPage | null) => void;

export class PageRegistry {
  private pages = new Map<number, MountedPage>();
  private waiters = new Map<number, Waiter[]>();

  mount(pageNo: number, root: HTMLElement, evidenceRoot: HTMLElement | null): void {
    const previous = this.pages.get(pageNo);
    this.pages.set(pageNo, {
      pageNo,
      root,
      evidenceRoot,
      // 挂载时先沿用上一次的视口尺寸：同一 scale 下重挂不需要重算
      viewport: previous?.viewport ?? null,
    });
  }

  unmount(pageNo: number): void {
    this.pages.delete(pageNo);
  }

  markRendered(pageNo: number, viewport: Size): void {
    const page = this.pages.get(pageNo);
    // 渲染异步完成时页面可能已被卸载（快速滚动），此时丢弃结果即可
    if (!page) return;
    page.viewport = viewport;
    for (const waiter of this.waiters.get(pageNo) ?? []) waiter(page);
    this.waiters.delete(pageNo);
  }

  rendered(pageNo: number): MountedPage | null {
    const page = this.pages.get(pageNo);
    return page?.viewport ? page : null;
  }

  /** 等某一页被画出来；超时返回 null，由调用方降级为「只滚动到页 + 提示」 */
  waitFor(pageNo: number, timeoutMs = 4000): Promise<MountedPage | null> {
    return new Promise<MountedPage | null>((resolve) => {
      let settled = false;
      const finish = (page: MountedPage | null) => {
        if (settled) return;
        settled = true;
        resolve(page);
      };
      const list = this.waiters.get(pageNo) ?? [];
      list.push(finish);
      this.waiters.set(pageNo, list);
      window.setTimeout(() => {
        // 超时后把自己摘掉，否则这个回调会一直挂在表里等下一次渲染
        const current = this.waiters.get(pageNo);
        if (current) this.waiters.set(pageNo, current.filter((item) => item !== finish));
        finish(null);
      }, timeoutMs);
    });
  }

  /**
   * 缩放/容器尺寸变化后调用：canvas 尺寸变了，旧视口尺寸全部作废。
   *
   * 不清掉的话，定位会拿着旧尺寸算矩形，表现为「高亮框比例对但整体偏移」。
   */
  invalidate(): void {
    for (const page of this.pages.values()) page.viewport = null;
  }
}

/** 每份文档一个登记表；用 ref 保证重渲染不会换实例。 */
export function usePageRegistry(): PageRegistry {
  const ref = useRef<PageRegistry | null>(null);
  if (ref.current === null) ref.current = new PageRegistry();
  return ref.current;
}