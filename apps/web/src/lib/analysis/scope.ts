import type { AnalysisScope } from "@/types/knowledge";

/** 占比文案只认 kind 与标段引用；独立记录的 scope 不含 lot_ids，也能直接传入。 */
export type ScopeText = Pick<AnalysisScope, "kind" | "lot_refs"> & { lot_ids?: number[] };

/**
 * 适用范围措辞只维护一处：业务数据面板与专题结果必须给出同一句结论，
 * 否则同一条记录在两个视图里会被读成不同范围。
 */
export function scopeLabel(scope: ScopeText, lotTitle?: (id: number) => string | undefined): string {
  if (scope.kind === "common") return "公共要求";
  if (scope.kind === "unknown") return "归属待确认"
    + (scope.lot_refs.length ? `（原文指向：${scope.lot_refs.join("、")}）` : "");
  // 有标段目录时优先显示正式名称，读取不到再退回原始引用，避免界面出现空串。
  const names = (scope.lot_ids ?? []).map((id, index) =>
    lotTitle?.(id) ?? scope.lot_refs[index] ?? "标段待确认");
  return (names.length ? names : scope.lot_refs).join("、");
}
