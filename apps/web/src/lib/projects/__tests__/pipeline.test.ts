import { describe, expect, it } from "vitest";

import { derivePipeline, needsExtractRerun, needsReparse, type PipelineInput } from "../pipeline";

function input(overrides: Partial<PipelineInput> = {}): PipelineInput {
  return {
    version_id: 7,
    parse_status: "completed",
    extraction_status: "completed",
    extraction_count: 12,
    review_count: 0,
    ...overrides,
  };
}

describe("derivePipeline", () => {
  it("上传已排队但没有 PDF 版本时持续轮询，转换失败后停止", () => {
    const file = input({ version_id: null, parse_status: null, extraction_status: null,
      extraction_count: 0, latest_job: { status: "pending", stage: "converting" } });
    expect(derivePipeline(file)).toMatchObject({ inFlight: true, headline: "排队转换" });
    expect(derivePipeline({ ...file, latest_job: { status: "failed", stage: "converting" } }))
      .toMatchObject({ inFlight: false, tone: "failed", headline: "转换失败" });
  });

  it("仅归档文件没有转换任务，不会永久等待或轮询", () => {
    expect(derivePipeline(input({ is_parseable: false, version_id: null })))
      .toMatchObject({ inFlight: false, headline: "仅归档" });
  });

  it("重解析已排队但旧 parse_run 仍成功时，以新任务状态为准", () => {
    const view = derivePipeline(input({ latest_job: { status: "pending", stage: "submitting" } }));
    expect(view.inFlight).toBe(true);
    expect(view.stages.map((stage) => stage.state)).toEqual(["done", "active", "idle"]);
  });

  it("已有部分结果不能掩盖抽取中的任务或失败状态", () => {
    expect(derivePipeline(input({ extraction_status: "running", extraction_count: 3 })))
      .toMatchObject({ inFlight: true, headline: "抽取中" });
    expect(derivePipeline(input({ extraction_status: "failed", extraction_count: 3 })))
      .toMatchObject({ inFlight: false, tone: "failed", headline: "抽取失败" });
  });
  it("没有版本时停在转换，后面的阶段一律不亮", () => {
    const view = derivePipeline(
      input({ version_id: null, parse_status: null, extraction_status: null, extraction_count: 0 }),
    );
    expect(view.stages.map((stage) => stage.state)).toEqual(["idle", "idle", "idle"]);
    expect(view.headline).toBe("等待转换");
    expect(view.inFlight).toBe(false);
  });

  it("解析完成但抽取没跑：轨迹完整，抽取显示等待", () => {
    const view = derivePipeline(input({ extraction_status: null, extraction_count: 0 }));
    expect(view.stages.map((stage) => stage.state)).toEqual(["done", "done", "idle"]);
    expect(view.headline).toBe("等待抽取");
    expect(view.inFlight).toBe(false);
  });

  it("抽取排队中算在途，列表页要据此轮询", () => {
    const view = derivePipeline(input({ extraction_status: "pending", extraction_count: 0 }));
    expect(view.tone).toBe("active");
    expect(view.headline).toBe("排队抽取");
    expect(view.inFlight).toBe(true);
  });

  it("解析失败后抽取不再显示失败（它根本没开始）", () => {
    const view = derivePipeline(
      input({ parse_status: "failed", extraction_status: "failed", extraction_count: 0 }),
    );
    expect(view.stages.map((stage) => stage.state)).toEqual(["done", "failed", "idle"]);
    expect(view.headline).toBe("解析失败");
    expect(view.tone).toBe("failed");
  });

  it("并发的陈旧抽取状态不会拼出「解析中 + 抽取完成」", () => {
    const view = derivePipeline(
      input({ parse_status: "running", extraction_status: "completed", extraction_count: 5 }),
    );
    expect(view.stages.map((stage) => stage.state)).toEqual(["done", "active", "idle"]);
  });

  it("完成但有待复核时，headline 报到待复核条数上", () => {
    const view = derivePipeline(input({ review_count: 3 }));
    expect(view.tone).toBe("done");
    expect(view.headline).toBe("3 项待复核");
  });

  it("解析部分成功也算完成（partial 不是失败）", () => {
    const view = derivePipeline(input({ parse_status: "partial" }));
    expect(view.stages[1]?.state).toBe("done");
  });
});

describe("重跑入口的可点条件", () => {
  it("解析成功、抽取失败：给「重跑抽取」而不是「重新解析」", () => {
    const file = input({ extraction_status: "failed", extraction_count: 0 });
    expect(needsExtractRerun(file)).toBe(true);
    expect(needsReparse(file)).toBe(false);
  });

  it("抽取 job 从没建过（状态为空）也算没产出", () => {
    expect(needsExtractRerun(input({ extraction_status: null, extraction_count: 0 }))).toBe(true);
  });

  it("解析没成时不建议重跑抽取：抽取要拿 element 当输入，一定还会失败", () => {
    const file = input({ parse_status: "failed", extraction_status: null, extraction_count: 0 });
    expect(needsExtractRerun(file)).toBe(false);
    expect(needsReparse(file)).toBe(true);
  });

  it("已经有结果时不给整份重抽入口（那属于按字段补跑）", () => {
    expect(needsExtractRerun(input({ extraction_status: "failed" }))).toBe(false);
  });

  it("抽取正在跑时不重复排队", () => {
    expect(
      needsExtractRerun(input({ extraction_status: "running", extraction_count: 0 })),
    ).toBe(false);
  });

  it("没有版本的文件两个入口都不给", () => {
    const file = input({
      version_id: null,
      parse_status: null,
      extraction_status: null,
      extraction_count: 0,
    });
    expect(needsExtractRerun(file)).toBe(false);
    expect(needsReparse(file)).toBe(false);
  });
});
