import type { AnalysisField, AnalysisModule, Citation } from "@/types/knowledge";

/** 同一块可支撑多个专题；回到刚才核对的事项，并避免同名元素跨版本串用。 */
export function findCitationResult(
  modules: AnalysisModule[],
  ref: Citation,
  activeItemId?: string,
  activeModuleId?: number | null,
) {
  const candidates = modules.flatMap((module) => module.items.flatMap((item) => {
    const matches = item.values.flatMap((value) => value.citations).filter((candidate) =>
      citationLocationKey(candidate) === citationLocationKey(ref));
    return matches.length ? [{ module, item, exact: matches.some((c) => c.quote === ref.quote) }] : [];
  }));
  return candidates.find(({ item }) => item.id === activeItemId)
    ?? candidates.find(({ module, exact }) => module.id === activeModuleId && exact)
    ?? candidates.find(({ exact }) => exact)
    ?? candidates.find(({ module }) => module.id === activeModuleId)
    ?? candidates[0];
}

/** 同一长元素可派生不同范围的大块；页码和真实区域共同确定位置，同区域仍合并。 */
export function citationLocationKey(ref: Citation): string {
  return JSON.stringify([ref.source_id, ref.version_id, ref.parse_run_id,
    ref.element_id, ref.page_no, ref.bbox]);
}

/** PDF角标与定位入口共用区域身份；选中的引用替换同区域摘录，不覆盖其他区域。 */
export function viewerCitations(citations: Citation[], selected: Citation): Citation[] {
  const locations = new Map<string, Citation>();
  for (const ref of citations) {
    if (ref.source_id === selected.source_id && ref.version_id === selected.version_id
      && ref.parse_run_id === selected.parse_run_id) locations.set(citationLocationKey(ref), ref);
  }
  locations.set(citationLocationKey(selected), selected);
  return [...locations.values()];
}

export function groupCitationLocations(refs: Citation[]) {
  const locations = new Map<string, { ref: Citation; quotes: Set<string> }>();
  for (const ref of refs) {
    const key = citationLocationKey(ref);
    const location = locations.get(key);
    const quotes = ref.excerpts ?? (ref.quote ? [ref.quote] : []);
    if (location) quotes.forEach((quote) => location.quotes.add(quote));
    else locations.set(key, { ref, quotes: new Set(quotes) });
  }
  return [...locations.values()];
}

/** 只分配展示入口，不改逐条证据绑定；同一事项内的位置归到首次出现的正文单元。 */
export function presentCitations(item: AnalysisField) {
  const content: Record<string, Citation[][]> = {};
  const extra: Citation[] = [];
  const owners = new Map<string, { refs: Citation[]; quotes: Set<string> }>();
  const assign = (refs: Citation[], target: Citation[]) => {
    for (const ref of refs) {
      const key = citationLocationKey(ref);
      let owner = owners.get(key);
      if (!owner) {
        owner = { refs: target, quotes: new Set() };
        owners.set(key, owner);
      }
      // 同位置的补充摘录也收进已有入口，避免去掉图标时一起丢掉条件和材料依据。
      if (!owner.quotes.has(ref.quote)) owner.refs.push(ref);
      owner.quotes.add(ref.quote);
    }
  };
  const output = item.output;
  if (output?.citations) {
    const paired = output.columns.length === 2 && output.columns[0] === "字段" && output.columns[1] === "内容";
    // 字段标签不画入口；评分的满分先于其它列展示，入口顺序与用户阅读顺序一致。
    const columns = paired ? ["内容"] : [
      ...output.columns.filter((column) => column === "满分分值"),
      ...output.columns.filter((column) => column !== "满分分值"),
    ];
    for (const column of columns) {
      const value = output.content[column];
      const lines = Array.isArray(value) ? value : value ? [value] : [];
      content[column] = lines.map((line, index) => {
        const refs: Citation[] = [];
        if (line) assign(output.citations?.[column]?.[index] ?? [], refs);
        return refs;
      });
    }
  }
  assign(item.values.flatMap((value) => value.citations), extra);
  return { content, extra };
}
