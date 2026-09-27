"use client";

/**
 * 证据索引的 React 包装：只做「依赖不可变数组 → 纯函数建索引」这一件事。
 *
 * 依赖整个数组而不是逐条：数据只在加载完成或重跑后整体替换（见 docs/工程/10 第 2 节），
 * 逐条比较反而会在原地修改时漏更新。
 */

import { useMemo } from "react";

import { buildEvidenceIndex, type EvidenceIndex } from "@/lib/viewer/evidenceIndex";
import type { WireExtraction } from "@/types/workbench";

export type { EvidenceIndex, EvidenceItem, EvidenceTarget } from "@/lib/viewer/evidenceIndex";
export { toActiveEvidence } from "@/lib/viewer/evidenceIndex";

export function useEvidenceIndex(extractions: readonly WireExtraction[]): EvidenceIndex {
  return useMemo(() => buildEvidenceIndex(extractions), [extractions]);
}