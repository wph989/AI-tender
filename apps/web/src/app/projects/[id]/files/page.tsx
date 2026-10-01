import { ProjectFiles } from "@/components/projects/ProjectFiles";

/**
 * 文件管理页（设计文档 06 第 1 节）：批量上传、角色维护、换内容、软删除。
 *
 * 与工作台分成两个路由，是因为两件事的节奏完全不同：上传是「把材料收进来」的一次性动作，
 * 核对是「反复来回看」的持续动作。放在一页里，核对时左边永远挂着一个上传区。
 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const projectId = Number(id);
  if (!Number.isSafeInteger(projectId) || projectId < 1) {
    return <div className="p-8 text-[14px] text-rose-700">项目 ID 无效</div>;
  }
  return <ProjectFiles projectId={projectId} />;
}