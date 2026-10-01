/**
 * 复核队列的排序与「要人处理」的口径（见 docs/设计/06 第 11 节的复核模式）。
 *
 * 为什么是排序而不是过滤：复核时仍要随时切回「全部结果」看上下文。两个视图共用
 * 同一份数据、只换顺序，切来切去不会丢位置感，也不会出现「切回全部后发现少了几条」。
 *
 * 优先级按「这条会不会让评审出错」排，不按状态听起来有多严重：
 *   冲突     两份文件给出不同的值，必须人裁决，排第一；
 *   待复核   机器自己不确定；
 *   自动     机器有把握，但默认没人看过；
 *   已确认   用户已经处理过；
 *   已驳回   用户明确否掉的，回顾用；
 *   未找到   没有可核对的值，排最后——放前面只会挤掉真正能看的条目。
 */

import type { ExtractionStatus, WireExtraction } from "@/types/workbench";

const REVIEW_PRIORITY: Record<ExtractionStatus, number> = {
  conflict: 0,
  need_review: 1,
  auto: 2,
  verified: 3,
  rejected: 4,
  not_found: 5,
};

/** 未知状态按自动档处理：宁可排在中间，也不要因为后端加了枚举就掉出列表。 */
function priority(item: WireExtraction): number {
  return REVIEW_PRIORITY[item.status] ?? REVIEW_PRIORITY.auto;
}

export function orderForReview(items: readonly WireExtraction[]): WireExtraction[] {
  // sort 稳定：同优先级保持接口顺序（抽取顺序），重跑后不会整屏乱跳。
  return [...items].sort((a, b) => priority(a) - priority(b));
}

/**
 * 需要用户动作的条数：冲突 + 待复核。
 *
 * 口径只写这一处：统计条、分组标签上的琥珀色圆点、标签页排序都消费它，
 * 各写各的必然出现「统计条说 3 条、点进去只找到 2 条」。
 */
export function needsActionCount(items: readonly WireExtraction[]): number {
  return items.filter((item) => item.status === "need_review" || item.status === "conflict").length;
}
