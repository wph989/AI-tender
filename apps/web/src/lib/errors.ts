/** 通用小工具：错误文案兜底（后端错误 message 已在各 API 客户端里提取过）。 */

export function message(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}