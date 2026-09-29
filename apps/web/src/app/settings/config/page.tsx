import { ConfigCenter } from "@/components/config/ConfigCenter";

/**
 * 配置中心页（设计文档 08）：三层配置、版本发布、门禁与审计。
 *
 * 与模型管理同级：运行期参数的变更需要审计与回滚，不该混在解析工作台里。
 */
export default function Page() {
  return <ConfigCenter />;
}