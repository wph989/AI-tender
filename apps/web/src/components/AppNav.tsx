"use client";

/**
 * 顶部导航：工作台 / 模型管理 / 配置中心（设计文档 08、12 第 8 节）。
 *
 * 做成可嵌入的行内组件而不是 layout 里的全局顶栏：工作台用 h-screen 全屏布局，
 * 外面再套一层固定顶栏会把视口撑破。两处顶栏各放一份，导航内容只有这一份实现。
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "工作台" },
  { href: "/settings/models", label: "模型管理" },
  { href: "/settings/config", label: "配置中心" },
] as const;

export function AppNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-3">
      <span className="text-sm font-semibold text-slate-800">AI-Tender</span>
      <div className="flex items-center gap-1">
        {LINKS.map((link) => {
          const active =
            link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={
                active
                  ? "rounded bg-slate-900 px-2 py-1 text-xs text-white"
                  : "rounded px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
              }
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}