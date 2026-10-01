/**
 * 证据内存索引：点击结果 → 高亮可见的 300ms 预算全靠它（见 docs/设计/06 第 10 节）。
 *
 * 为什么在前端整份建索引、而不是挨条去调接口：定位发生在点击瞬间，一次网络往返就能吃掉一半预算；
 * 证据量级在几百条，整份索引的内存开销可以忽略——接口只负责下发数据，索引是纯派生计算。
 *
 * 为什么拆成两个视图：
 *  - byPage：原文视图按页取，**只收 bbox 合法的证据**——画不出框的硬画只会得到错位高亮；
 *  - byExtraction：结果面板按结果取，含 bbox 为空的证据，它们仍可降级为「页级定位」（见 06 第 5 节边界表）。
 * 一次遍历同时产出两者，避免两处各筛一遍导致口径漂移。
 */

import { toBbox } from "@/lib/api/wire";
import type { Bbox } from "@/lib/coords/bbox";
import type { ActiveEvidence } from "@/lib/store/viewerStore";
import type { WireExtraction } from "@/types/workbench";

export interface EvidenceTarget {
  extractionId: number;
  anchor: string;
  pageNo: number;
  /** null = 只有页级定位（bbox 缺失或非法），此时不画矩形，改为整页边框闪一下 */
  bbox: Bbox | null;
  fieldKey: string;
  label: string;
  /** 证据引文：结果面板的证据列表要展示"这处证据写了什么"（见 06 第 2.1 节） */
  quote: string;
}

/** 能画出来的证据：bbox 一定合法，EvidenceLayer 直接拿它做乘法。 */
export interface EvidenceItem extends EvidenceTarget {
  bbox: Bbox;
  /**
   * 页内角标编号（从 1 起）：原文页上那个数字气泡靠它，点角标即反向定位（06 第 11 节）。
   *
   * 为什么在建索引时定死、而不是渲染时按数组下标算：虚拟滚动会反复挂载卸载页面，
   * 渲染时算会在滚动过程中变号，用户刚记住的「第 3 处」就指到别的地方了。
   */
  badge: number;
}

export interface EvidenceIndex {
  byPage: Map<number, EvidenceItem[]>;
  byExtraction: Map<number, EvidenceTarget[]>;
}

export function buildEvidenceIndex(extractions: readonly WireExtraction[]): EvidenceIndex {
  const byPage = new Map<number, EvidenceItem[]>();
  const byExtraction = new Map<number, EvidenceTarget[]>();

  for (const extraction of extractions) {
    // 中文名优先用接口下发的字段定义；样本数据自带 field_label，真实接口由字段表提供
    const label = extraction.field_label ?? extraction.field_key;
    const targets: EvidenceTarget[] = [];

    for (const evidence of extraction.evidence) {
      const bbox = toBbox(evidence.bbox);
      const target: EvidenceTarget = {
        extractionId: extraction.id,
        anchor: evidence.anchor,
        pageNo: evidence.page_no,
        bbox,
        fieldKey: extraction.field_key,
        label,
        quote: evidence.quote,
      };
      targets.push(target);

      if (bbox === null) continue;
      const list = byPage.get(evidence.page_no);
      // 编号只数**画得出来**的证据：画不出框的条目在原文页上没有落点，不该占号。
      const item: EvidenceItem = { ...target, bbox, badge: (list?.length ?? 0) + 1 };
      if (list === undefined) byPage.set(evidence.page_no, [item]);
      else list.push(item);
    }

    byExtraction.set(extraction.id, targets);
  }

  return { byPage, byExtraction };
}

/** 结果面板 → 定位时序的输入。集中转换，避免面板各处自己拼、漏掉 label 导致提示语为空。 */
export function toActiveEvidence(target: EvidenceTarget): ActiveEvidence {
  return {
    extractionId: target.extractionId,
    anchor: target.anchor,
    pageNo: target.pageNo,
    bbox: target.bbox,
    label: target.label,
  };
}