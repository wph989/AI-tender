"use client";

/**
 * 左侧导航栏：全站的「卷宗脊」。
 *
 * 为什么导航从顶栏挪到左侧竖栏：顶栏只有 40px 高，塞进品牌、面包屑和动作区之后
 * 每一块都被压成一行小字，看起来像后台模板。竖栏把这几个入口从横向的空间竞争里
 * 拿出来，内容区因此能通栏，工作台的原文也就能真正占满宽度。
 *
 * 为什么是深色：它对应档案柜里那一排卷宗的**书脊**——竖着的一条深色脊，上面贴着
 * 亮色的分类标。内容区是纸，导航是脊，这个对比在每一页都对同一个事实说话：
 * 你在这里翻的是别人的投标材料。
 *
 * 商标不用图形 logo：「标」字 + 下面那道荧光笔痕，既是字标又是本产品唯一的
 * 装饰记号（和原文里的证据高亮同色），全站的装饰只允许有这一笔。
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DATA_CLASS } from "@/components/ui";

/** 三个入口按「先干活、后调参」排：项目在前，模型与配置是运维动作。 */
const NAV = [
  { href: "/projects", label: "项目", Icon: DossierIcon },
  { href: "/settings/models", label: "模型", Icon: ModelIcon },
  { href: "/settings/config", label: "配置", Icon: ConfigIcon },
] as const;

export function AppRail() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="主导航"
      className="flex w-[92px] shrink-0 flex-col bg-slate-900 select-none"
    >
      <Link
        href="/projects"
        className="flex flex-col items-center gap-2.5 pt-6 pb-7"
        title="AI-Tender · 招标文件解析与溯源"
      >
        <span className="relative flex h-11 w-11 items-center justify-center bg-slate-950 ring-1 ring-white/12">
          <span className="font-serif text-[22px] leading-none text-white">标</span>
          <span aria-hidden className="absolute inset-x-0 bottom-0 h-[3px] bg-amber-400" />
        </span>
        <span className="text-[11px] tracking-tight text-slate-500">AI-Tender</span>
      </Link>

      <div className="flex flex-col">
        {NAV.map(({ href, label, Icon }) => {
          // 工作台挂在 /projects/[id] 下，用前缀匹配才能让「项目」在子页面上也保持选中。
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={
                "relative flex flex-col items-center gap-2 py-4 text-[12px] leading-none " +
                "transition-colors " +
                (active
                  ? "bg-slate-800 font-medium text-white"
                  : "text-slate-500 hover:bg-white/5 hover:text-slate-200")
              }
            >
              {active && (
                <span aria-hidden className="absolute inset-y-0 left-0 w-[4px] bg-amber-400" />
              )}
              <Icon />
              <span>{label}</span>
            </Link>
          );
        })}
      </div>

      {/*
       * 底部只放一句部署事实，不放「运行正常」之类的状态灯：
       * 前端拿不到完整的服务健康信息，画一个假绿灯比不画更糟。
       * 「内网版」是这个产品的硬约束（原件不出内网），用户需要知道这件事。
       */}
      <div className="mt-auto flex flex-col items-center gap-1 pb-5">
        <span aria-hidden className="h-[3px] w-[3px] rounded-full bg-slate-700" />
        <span className={DATA_CLASS + " text-[11px] text-slate-600"}>内网版</span>
      </div>
    </nav>
  );
}

function DossierIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3.5 6.5A1.5 1.5 0 0 1 5 5h3.4l1.4 2.2h9.2A1.5 1.5 0 0 1 20.5 8.7v8.8a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5z" />
    </svg>
  );
}

function ModelIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3 3.5 7.5 12 12l8.5-4.5z" />
      <path d="M3.5 12 12 16.5 20.5 12" />
      <path d="M3.5 16.5 12 21l8.5-4.5" />
    </svg>
  );
}

function ConfigIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 7.5h16M4 16.5h16" />
      <circle cx="9.5" cy="7.5" r="2" fill="currentColor" stroke="none" />
      <circle cx="15" cy="16.5" r="2" fill="currentColor" stroke="none" />
    </svg>
  );
}
