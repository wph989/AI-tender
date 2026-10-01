/**
 * 展示层格式化：字节、时间、计数。
 *
 * 为什么集中在一处：同一个数值在列表页写「12.3 MB」、在上传区写「12.34MB」，
 * 用户会以为两个地方量的不是同一个东西。格式只允许有一个定义。
 */

/** 二进制单位（1 KiB = 1024）；招投标文件动辄几百 MB，用 MiB 更贴近存储侧口径。 */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[index]}`;
}

/**
 * 后端一律回 UTC 的 ISO 串；用浏览器本地时区显示，并压到「刚刚 / N 分钟前 / 日期」三档。
 * 精确到秒的时间只在追溯链里有意义，列表里只会制造噪声。
 */
export function formatTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "—";
  const diff = now - at;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  const date = new Date(at);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}