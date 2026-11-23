import { describe, expect, it } from "vitest";

import { derivePipeline, type PipelineInput } from "../pipeline";

function input(overrides: Partial<PipelineInput> = {}): PipelineInput {
  return { version_id: 7, parse_status: "completed", ...overrides };
}

describe("文件转换与解析", () => {
  it("上传排队时持续轮询，转换失败后停止", () => {
    const file = input({ version_id: null, parse_status: null,
      latest_job: { status: "pending", stage: "converting" } });
    expect(derivePipeline(file)).toMatchObject({ inFlight: true, headline: "排队转换" });
    expect(derivePipeline({ ...file, latest_job: { status: "failed", stage: "converting" } }))
      .toMatchObject({ inFlight: false, tone: "failed", headline: "转换失败" });
  });

  it("归档文件和尚未创建转换任务的文件不会永久轮询", () => {
    expect(derivePipeline(input({ is_parseable: false, version_id: null })))
      .toMatchObject({ inFlight: false, headline: "仅归档" });
    const view = derivePipeline(input({ version_id: null, parse_status: null }));
    expect(view.stages.map((stage) => stage.state)).toEqual(["idle", "idle"]);
    expect(view).toMatchObject({ inFlight: false, headline: "等待转换" });
  });

  it.each(["submitting", "parsing"])("新%s任务覆盖上次成功的解析状态", (stage) => {
    const view = derivePipeline(input({ latest_job: { status: "pending", stage } }));
    expect(view).toMatchObject({ inFlight: true, headline: "排队解析" });
    expect(view.stages.map((entry) => entry.state)).toEqual(["done", "active"]);
    expect(derivePipeline(input({ latest_job: { status: "failed", stage } })))
      .toMatchObject({ inFlight: false, headline: "解析失败" });
  });

  it("转换完成后等待解析，解析就绪后进入项目分析", () => {
    expect(derivePipeline(input({ parse_status: null })))
      .toMatchObject({ inFlight: false, headline: "等待解析" });
    const view = derivePipeline(input());
    expect(view.stages.map((stage) => stage.key)).toEqual(["convert", "parse"]);
    expect(view).toMatchObject({ tone: "done", headline: "已就绪", inFlight: false });
  });

  it("运行、失败、取消和部分完成都有可终止的状态", () => {
    expect(derivePipeline(input({ parse_status: "running" })))
      .toMatchObject({ inFlight: true, headline: "解析中" });
    for (const status of ["failed", "canceled"]) {
      expect(derivePipeline(input({ parse_status: status })))
        .toMatchObject({ inFlight: false, tone: "failed" });
    }
    expect(derivePipeline(input({ parse_status: "partial" })))
      .toMatchObject({ inFlight: false, tone: "done", headline: "部分解析完成" });
  });
});
