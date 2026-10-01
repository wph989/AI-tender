import { Suspense } from "react";

import { ProjectWorkspace } from "@/components/projects/ProjectWorkspace";

/**
 * 项目工作台页（设计文档 06 第 1 节）。
 *
 * 包一层 Suspense 是因为内部的文件切换用 useSearchParams 读 ?file=：
 * 这个 hook 在预渲染阶段没有查询串，Next 要求调用方给出边界，否则整页会被判为不可静态化。
 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const projectId = Number(id);
  if (!Number.isSafeInteger(projectId) || projectId < 1) {
    return <div className="p-8 text-[14px] text-rose-700">项目 ID 无效</div>;
  }
  return (
    <Suspense fallback={<div className="p-8 text-[14px] text-slate-500">正在加载项目…</div>}>
      <ProjectWorkspace projectId={projectId} />
    </Suspense>
  );
}