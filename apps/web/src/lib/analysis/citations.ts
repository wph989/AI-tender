import type { AnalysisModule, Citation } from "@/types/knowledge";

/** 同一块可支撑多个专题；回到刚才核对的事项，并避免同名元素跨版本串用。 */
export function findCitationResult(
  modules: AnalysisModule[],
  ref: Citation,
  activeItemId?: string,
  activeModuleId?: number | null,
) {
  const candidates = modules.flatMap((module) => module.items.flatMap((item) => {
    const matches = item.values.flatMap((value) => value.citations).filter((candidate) =>
      candidate.source_id === ref.source_id && candidate.version_id === ref.version_id
      && candidate.parse_run_id === ref.parse_run_id && candidate.element_id === ref.element_id,
    );
    return matches.length ? [{ module, item, exact: matches.some((c) => c.quote === ref.quote) }] : [];
  }));
  return candidates.find(({ item }) => item.id === activeItemId)
    ?? candidates.find(({ module, exact }) => module.id === activeModuleId && exact)
    ?? candidates.find(({ exact }) => exact)
    ?? candidates.find(({ module }) => module.id === activeModuleId)
    ?? candidates[0];
}
