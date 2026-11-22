import { ModelSettings } from "@/components/llm/ModelSettings";

/**
 * 模型管理页（docs/设计/12-LLM管理与模型路由.md）：供应商、模型、功能绑定三块。
 *
 * 与工作台同级的独立路由：模型配置是运维动作，不该混在解析工作台里。
 */
export default function Page() {
  return <ModelSettings />;
}