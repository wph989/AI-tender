import type { Bbox } from "@/lib/coords/bbox";

/** 原文定位只接收证据身份，不依赖任何业务结果模型。 */
export interface EvidenceTarget {
  evidenceId: number;
  anchor: string;
  pageNo: number;
  bbox: Bbox | null;
  label: string;
  quote: string;
}

export interface EvidenceItem extends EvidenceTarget {
  bbox: Bbox;
  badge: number;
}

export interface EvidenceIndex {
  byPage: Map<number, EvidenceItem[]>;
  byEvidence: Map<number, EvidenceTarget[]>;
}
