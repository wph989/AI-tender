"use client";

/**
 * 普通页面的外框：左侧导航 + 页头（栏目 / 标题 / 说明 / 动作）+ 居中主体。
 *
 * 为什么单独抽出来：项目列表、文件管理、模型管理、配置中心是同一类页面。
 * 每个页面各写一遍页头，改一次间距就要改四遍，改漏的那个页面看起来会像「另一个产品」。
 *
 * 标题用宋体、栏目用小号字距字：一份公文的第一行永远是「×××关于×××的通知」，
 * 上面那行小字是发文机关。把页头排成这个结构，用户一眼就知道自己在哪一页、
 * 这一页要他干什么。
 *
 * 面包屑是可选的：只有真的存在层级（项目 ▸ 名称 ▸ 文件）的页面才传，
 * 顶层页传了反而会多出一行只有一项的假层级。
 */

import type { ReactNode } from "react";

import { AppRail } from "@/components/AppRail";
import { EYEBROW_CLASS } from "@/components/ui";

interface Props {
  /**
   * 面包屑：按顺序给层级，分隔符由这里统一渲染（调用方各写一遍必然出现两种箭头）。
   * 不传就完全不渲染这一行。
   */
  breadcrumb?: readonly ReactNode[];
  /** 页头左上角的小字，例如「项目」。 */
  eyebrow: string;
  title: ReactNode;
  /** 标题下的一句话说明：这一页是干什么的、下一步该做什么。 */
  description?: ReactNode;
  /** 右侧动作区。 */
  actions?: ReactNode;
  /** 主体最大宽度：清单页要宽，设置页收窄更好读。 */
  width?: "wide" | "narrow";
  children: ReactNode;
}

const WIDTH_CLASS: Record<NonNullable<Props["width"]>, string> = {
  wide: "max-w-[1680px]",
  narrow: "max-w-[1180px]",
};

export function PageShell({
  breadcrumb,
  eyebrow,
  title,
  description,
  actions,
  width = "wide",
  children,
}: Props) {
  return (
    <div className="flex min-h-screen">
      <AppRail />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-slate-200 bg-white">
          <div
            className={
              "mx-auto flex w-full flex-wrap items-end justify-between gap-x-8 gap-y-3 px-10 pt-8 pb-6 2xl:px-14 " +
              WIDTH_CLASS[width]
            }
          >
            <div className="min-w-0">
              {breadcrumb !== undefined && breadcrumb.length > 0 && (
                <nav
                  aria-label="面包屑"
                  className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[13px] text-slate-400"
                >
                  {breadcrumb.map((segment, index) => (
                    <span key={index} className="flex items-center gap-1.5">
                      {index > 0 && (
                        <span aria-hidden className="text-slate-300">
                          ▸
                        </span>
                      )}
                      {segment}
                    </span>
                  ))}
                </nav>
              )}
              <p className={EYEBROW_CLASS}>{eyebrow}</p>
              <h1 className="mt-1.5 font-serif text-[34px] leading-[44px] text-slate-900">
                {title}
              </h1>
              {description !== undefined && (
                <div className="mt-2 max-w-3xl text-[14px] leading-6 text-slate-500">
                  {description}
                </div>
              )}
            </div>
            {actions !== undefined && (
              <div className="flex flex-wrap items-center gap-2">{actions}</div>
            )}
          </div>
        </header>
        <main
          className={
            "sheet-in mx-auto flex w-full flex-1 flex-col gap-7 px-10 py-7 2xl:px-14 " + WIDTH_CLASS[width]
          }
        >
          {children}
        </main>
      </div>
    </div>
  );
}
