"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/Icon";

const NAV = [
  { href: "/projects", label: "项目空间", icon: "folder" },
  { href: "/knowledge", label: "知识库", icon: "book" },
  { href: "/settings/models", label: "模型管理", icon: "layers" },
  { href: "/settings/config", label: "配置中心", icon: "sliders" },
] as const;

/** 横向导航释放文档阅读宽度；前缀匹配让项目子页始终保留所属入口。 */
export function AppRail() {
  const pathname = usePathname();
  return (
    <header className="app-header">
      <a href="#main-content" className="skip-link">跳到主要内容</a>
      <div className="app-header-inner">
        <Link href="/projects" className="brand" aria-label="AI-Tender 首页">
          <span className="brand-symbol"><Icon name="scan" size={23} /></span>
          <span className="brand-name">AI<span>·</span>Tender</span>
          <span className="brand-caption">招标智能分析</span>
        </Link>
        <nav aria-label="主导航" className="main-nav">
          {NAV.map(({ href, label, icon }) => (
            <Link key={href} href={href} aria-current={pathname.startsWith(href) ? "page" : undefined}>
              <Icon name={icon} size={17} /><span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="header-note"><Icon name="shield" size={15} /><span>私有部署</span></div>
      </div>
    </header>
  );
}
