/** 模型管理页共用的小工具：错误文案、时间与测试状态。 */

/** 后端错误体里的 message 已经在 lib/api/llm.ts 里提取过，这里只兜底非 Error 抛出。 */
export { message } from "@/lib/errors";

/** 只显示到分钟：配置页关心"什么时候测过"，秒没有意义。 */
export function formatTime(value: string | null): string {
  if (value === null || value === "") return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function validityLabel(state: string): string {
  return (
    (
      {
        valid: "通过 · 有效",
        failed: "失败",
        unknown: "结果未知，请核实供应商状态",
        running: "测试进行中",
        unsupported: "不支持目录，请单独测试模型",
        expired: "已过期，需重测",
        config_changed: "配置已变更，需重测",
        untested: "未测试",
      } as Record<string, string>
    )[state] ?? state
  );
}
export const kindLabel = {
  language: "Language · 语言",
  embedding: "Embedding · 嵌入",
  rerank: "Rerank · 重排",
  image_generation: "Image · 生图",
};

export const capabilityLabel: Record<string, string> = {
  text_input: "文本输入",
  image_input: "图片输入",
  json_output: "JSON 输出",
  embedding: "文本嵌入",
  rerank: "专用重排",
  image_generation: "图片生成",
  text: "文本",
  vision: "视觉",
  multimodal_embedding: "图文嵌入",
};

/** 页面按服务端范围提前反馈错误；未指定范围时仍检查数值及整数类型。 */
export function withinNumericRule(
  value: number, rule?: import("@/types/llm").ParameterSchema,
): boolean {
  return Number.isFinite(value) && (rule?.type !== "integer" || Number.isInteger(value)) &&
    (rule?.min === undefined || (rule.exclusive_min ? value > rule.min : value >= rule.min)) &&
    (rule?.max === undefined || value <= rule.max);
}

/** 限流冷却剩余时间：秒级数字对运维没有意义，按分秒给出可读的等待长度。 */
export function countdownLabel(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  if (total < 60) return `${total} 秒`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分钟`;
}
