"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Button, Drawer } from "antd";
import { Icon } from "@/components/Icon";

const NAV = [
  { href: "/projects", label: "项目空间", icon: "folder" },
  { href: "/knowledge", label: "知识库", icon: "book" },
  { href: "/settings/models", label: "模型管理", icon: "layers" },
  { href: "/settings/config", label: "配置中心", icon: "sliders" },
] as const;

/** 桌面导航固定在左侧，窄屏使用抽屉，把横向空间交还给文档与清单。 */
export function AppRail() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const links = <nav aria-label="主导航" className="main-nav">
    {NAV.map(({ href, label, icon }) => (
      <Link key={href} href={href} aria-current={pathname.startsWith(href) ? "page" : undefined}
        onClick={() => setOpen(false)}>
        <Icon name={icon} size={17} /><span>{label}</span>
      </Link>
    ))}
  </nav>;
  return (
    <>
    <aside className="app-header" aria-label="应用导航">
      <a href="#main-content" className="skip-link">跳到主要内容</a>
      <div className="app-header-inner">
        <Link href="/projects" className="brand" aria-label="AI-Tender 首页">
          <span className="brand-symbol"><Icon name="scan" size={23} /></span>
          <span className="brand-name">AI<span>·</span>Tender</span>
          <span className="brand-caption">招标智能分析</span>
        </Link>
        <div className="desktop-navigation">{links}</div>
        <Button className="mobile-menu-button" type="text" aria-label="打开导航菜单"
          aria-expanded={open} onClick={() => setOpen(true)} icon={<Icon name="list" />} />
        <div className="header-note"><Icon name="shield" size={15} /><span>私有部署</span></div>
      </div>
    </aside>
    <Drawer title="导航菜单" placement="left" open={open} onClose={() => setOpen(false)}
      size={260} destroyOnHidden>{links}</Drawer>
    </>
  );
}
