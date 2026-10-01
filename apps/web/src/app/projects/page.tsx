import { ProjectList } from "@/components/projects/ProjectList";

/**
 * 项目列表页（设计文档 06 第 1 节路由矩阵）。
 *
 * 它是整个系统的入口：工作台与文件管理都挂在某个项目下，
 * 没有这一层，用户打开系统只会看到一个不知道该操作什么的空工作台。
 */
export default function Page() {
  return <ProjectList />;
}