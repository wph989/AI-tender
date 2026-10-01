/**
 * 交件台逐文件结果的映射口径。
 *
 * 这条规则值得测试：它是「用户看到的每一行结论」的唯一来源，判错的方向又是最坏的那种——
 * 把没入库的文件标成已入库。
 */
import { describe, expect, it } from "vitest";

import { outcomeOf } from "@/lib/projects/upload";
import type { UploadResult } from "@/types/projects";

function result(partial: Partial<UploadResult>): UploadResult {
  return { added: [], jobs: [], skipped: [], ...partial };
}

function added(displayName: string): UploadResult["added"][number] {
  return {
    project_file_id: 1,
    display_name: displayName,
    role: "main",
    is_parseable: true,
    version_id: 1,
    job_id: null,
  };
}

describe("交件台逐文件结果", () => {
  it("出现在 added 里就是已入库", () => {
    expect(outcomeOf("招标文件.pdf", result({ added: [added("招标文件.pdf")] }))).toEqual({
      state: "added",
    });
  });

  it("出现在 skipped 里就带上服务端给的原因", () => {
    const outcome = outcomeOf(
      "假的.pdf",
      result({ skipped: [{ name: "假的.pdf", reason: "PDF 文件头无效" }] }),
    );
    expect(outcome).toEqual({ state: "skipped", reason: "PDF 文件头无效" });
  });

  // 压缩包不出现在 added 里（入库的是成员），不能因此判成未入库。
  it("ZIP 只要有成员入库，包本身就算成功", () => {
    expect(outcomeOf("材料.zip", result({ added: [added("主文件.pdf")] }))).toEqual({
      state: "added",
    });
  });

  it("ZIP 一个成员都没入库时不算成功", () => {
    expect(outcomeOf("材料.zip", result({}))).toEqual({ state: "unknown" });
  });

  it("两边都找不到就如实标未入库，不猜成成功", () => {
    expect(outcomeOf("没提到.pdf", result({ added: [added("另一个.pdf")] }))).toEqual({
      state: "unknown",
    });
  });
});
