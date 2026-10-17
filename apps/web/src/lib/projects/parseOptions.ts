import type { ParseTier } from "@/types/projects";

// 上传与配置页共用展示文案，提交值仍使用解析服务约定的枚举。
export const PARSE_TIERS: { value: ParseTier; label: string; description: string }[] = [
  { value: "flash", label: "快速预览", description: "用于快速浏览和检索，正式分析建议选择标准或增强解析。" },
  { value: "basic", label: "基础解析", description: "识别文字、公式和表格，适合版面简单的材料。" },
  { value: "standard", label: "标准解析", description: "适合日常招标文件，兼顾复杂版面和识别质量。" },
  { value: "advanced", label: "增强解析", description: "用于扫描质量差或表格复杂的材料，处理可能更慢。" },
];

export const OCR_MODES = [
  { value: "auto", label: "自动判断", description: "逐页判断是否需要图片文字识别，通常选此项。" },
  { value: "txt", label: "读取已有文字", description: "适合能直接选中文字的 PDF，不额外识别图片中的文字。" },
  { value: "ocr", label: "识别图片中的文字", description: "适合扫描件或拍照文件，逐页进行文字识别。" },
];
