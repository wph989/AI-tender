/**
 * 结果面板的分组标签模型（见 docs/设计/06 第 2.1 节）。
 *
 * 为什么从组件里搬出来：分组顺序、分组文案、待复核计数这三件事都有第二个消费方
 * （复核队列、统计条、将来的角标过滤），留在组件里各算各的必然漂移。
 *
 * 只出「有数据的分组」：空标签会让用户以为系统漏抽了，而不是"这组本来就没有"。
 */

import type { WireExtraction } from "@/types/workbench";

export const GROUP_LABELS: Record<string, string> = {
  basic_info: "基本信息",
  qualification: "资格要求",
  scoring: "评分办法",
  commercial: "商务条款",
  tech: "技术要求",
  risk: "风险条款",
};

/** 分组顺序按业务重要性固定：接口顺序是抽取顺序，用户核对顺序是业务顺序。 */
export const GROUP_ORDER = ["basic_info", "qualification", "scoring", "commercial", "tech", "risk"];

export interface ResultTab {
  key: string;
  label: string;
  items: WireExtraction[];
  /** 需要用户动作的条数：待复核 + 冲突。标签上的琥珀色圆点由它决定。 */
  pending: number;
  notFound: number;
}

function groupRank(key: string): number {
  const index = GROUP_ORDER.indexOf(key);
  return index === -1 ? GROUP_ORDER.length : index;
}

export function buildResultTabs(extractions: readonly WireExtraction[]): ResultTab[] {
  const groups = new Map<string, WireExtraction[]>();
  for (const extraction of extractions) {
    const list = groups.get(extraction.group_key);
    if (list === undefined) groups.set(extraction.group_key, [extraction]);
    else list.push(extraction);
  }
  // sort 是稳定排序：同组内保持接口给出的顺序（抽取顺序），卡片不会因切标签而重排
  return [...groups.entries()]
    .sort(([a], [b]) => groupRank(a) - groupRank(b))
    .map(([key, items]) => ({
      key,
      label: GROUP_LABELS[key] ?? key,
      items,
      pending: items.filter((item) => item.status === "need_review" || item.status === "conflict")
        .length,
      notFound: items.filter((item) => item.status === "not_found").length,
    }));
}