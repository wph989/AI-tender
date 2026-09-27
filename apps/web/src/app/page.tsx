import { DocumentWorkbench } from "@/components/workbench/DocumentWorkbench";

/**
 * 本切片只有工作台一个页面。
 * 路由矩阵里的项目列表、文件管理、复核队列、配置中心依赖后端接口，见 docs/设计/06 第 1 节。
 */
export default function Page() {
  return <DocumentWorkbench />;
}