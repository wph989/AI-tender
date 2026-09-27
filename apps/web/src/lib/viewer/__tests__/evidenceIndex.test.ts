/**
 * 证据索引是「点击 → 高亮 < 300ms」的性能基础，也是定位目标唯一的来源，
 * 所以它的筛选口径必须锁死：非法 bbox 不进原文视图，但仍保留在结果面板的定位目标里。
 */
import { describe, expect, it } from "vitest";

import { buildEvidenceIndex, cycleEvidence, toActiveEvidence } from "@/lib/viewer/evidenceIndex";
import type { WireExtraction } from "@/types/workbench";

function makeExtraction(input: {
  id: number;
  fieldKey: string;
  label?: string;
  evidence: { anchor: string; pageNo: number; bbox: readonly number[] }[];
}): WireExtraction {
  return {
    id: input.id,
    instance_id: input.id * 10,
    machine_attempt_no: 1,
    attempt_no: 1,
    trigger: "first",
    is_current: true,
    field_key: input.fieldKey,
    field_label: input.label,
    group_key: "basic_info",
    value_text: "值",
    confidence: 0.9,
    status: "auto",
    evidence_count: input.evidence.length,
    evidence: input.evidence.map((item) => {
      const [x0 = 0, y0 = 0, x1 = 1, y1 = 1] = item.bbox;
      return {
        anchor: item.anchor,
        page_no: item.pageNo,
        bbox: [x0, y0, x1, y1] as [number, number, number, number],
        char_start: 0,
        char_end: 1,
        quote: "q",
        quote_source: "native",
        match_type: "exact",
      };
    }),
  };
}

describe('buildEvidenceIndex', () => {
  it("按页归组，且只收 bbox 合法的证据", () => {
    const index = buildEvidenceIndex([
      makeExtraction({
        id: 1,
        fieldKey: "tender_no",
        label: "招标编号",
        evidence: [
          { anchor: "p2b1", pageNo: 2, bbox: [0.1, 0.1, 0.3, 0.15] },
          { anchor: "p2b2", pageNo: 2, bbox: [0.4, 0.1, 0.3, 0.15] }, // x1 < x0：非法
          { anchor: "p3b1", pageNo: 3, bbox: [0.1, 0.2, 0.5, 0.25] },
        ],
      }),
    ]);

    expect(index.byPage.get(2)?.map((item) => item.anchor)).toEqual(["p2b1"]);
    expect(index.byPage.get(3)?.map((item) => item.anchor)).toEqual(["p3b1"]);
    // 非法 bbox 的证据仍然留在定位目标里（降级为页级定位）
    expect(index.byExtraction.get(1)?.map((item) => item.bbox === null)).toEqual([false, true, false]);
  });

  it("字段中文名缺失时退回 field_key，方便提示语统一取用", () => {
    const index = buildEvidenceIndex([
      makeExtraction({
        id: 7,
        fieldKey: "max_price",
        evidence: [{ anchor: "p1b1", pageNo: 1, bbox: [0.1, 0.1, 0.2, 0.2] }],
      }),
    ]);
    expect(index.byExtraction.get(7)?.[0]?.label).toBe("max_price");
    expect(toActiveEvidence(index.byExtraction.get(7)![0]!).label).toBe("max_price");
  });

  it("没有证据的结果不产生任何定位目标", () => {
    const index = buildEvidenceIndex([makeExtraction({ id: 9, fieldKey: "x", evidence: [] })]);
    expect(index.byExtraction.get(9)).toEqual([]);
    expect(index.byPage.size).toBe(0);
  });
});

describe("cycleEvidence", () => {
  const targets = [
    { extractionId: 1, anchor: "p1b1", pageNo: 1, bbox: null, fieldKey: "a", label: "a" },
    { extractionId: 1, anchor: "p1b2", pageNo: 1, bbox: null, fieldKey: "a", label: "a" },
  ];

  it("多次点击按证据循环", () => {
    expect(cycleEvidence(targets, 0)?.anchor).toBe("p1b1");
    expect(cycleEvidence(targets, 1)?.anchor).toBe("p1b2");
    expect(cycleEvidence(targets, 2)?.anchor).toBe("p1b1");
  });

  it("没有证据时返回 null，而不是抛错", () => {
    expect(cycleEvidence([], 0)).toBeNull();
  });
});