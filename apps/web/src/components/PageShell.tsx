"use client";
import type { ReactNode } from "react";
import { Icon } from "@/components/Icon";

interface Props {
  breadcrumb?: readonly ReactNode[];
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  width?: "wide" | "narrow";
  children: ReactNode;
}

/** 页头与内容使用同一条对齐线，窄屏只改变边距，不改变信息顺序。 */
export function PageShell({ breadcrumb, eyebrow, title, description, actions, width = "wide", children }: Props) {
  return (
    <div className="page-shell">
      <main id="main-content" tabIndex={-1} className={"page-content sheet-in " + (width === "narrow" ? "page-content-narrow" : "")}>
        <header className="page-heading">
          <div className="min-w-0">
            <nav aria-label="面包屑" className="breadcrumb">
              {breadcrumb?.length ? breadcrumb.map((segment, index) => <span key={index}>{index > 0 && <Icon name="chevron" size={12} />}{segment}</span>) : <span>工作空间<Icon name="chevron" size={12} />{eyebrow}</span>}
            </nav>
            <h1>{title}</h1>
            {description && <div className="page-description">{description}</div>}
          </div>
          {actions && <div className="page-actions">{actions}</div>}
        </header>
        {children}
        <footer className="page-footer"><span>AI-Tender · 招标文件解析与溯源</span><span>每一条结论，都有据可查。</span></footer>
      </main>
    </div>
  );
}
