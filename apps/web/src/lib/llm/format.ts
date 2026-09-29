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

/** `last_test_status` 是自由文本列，只认识这两种取值，其余原样显示。 */
export function testLabel(status: string | null): string {
  if (status === "ok") return "通过";
  if (status === "error") return "失败";
  if (status === null || status === "") return "未测";
  return status;
}