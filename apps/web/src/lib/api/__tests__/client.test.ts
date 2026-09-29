/**
 * 导出文件名的解析口径。
 *
 * 后端对中文名走 RFC 5987 的 filename*（见 api/storage.py 的 content_disposition），
 * 只读 filename= 会拿到被下划线替换过的名字——用户看到的文件名会变成 "______-____.xlsx"。
 */
import { describe, expect, it } from "vitest";

import { filenameFromDisposition } from "@/lib/api/client";

describe("Content-Disposition 文件名解析", () => {
  it("优先取 filename*（中文名走这条）", () => {
    const name = "某项目-抽取结果.xlsx";
    // 用 encodeURIComponent 现场编码，避免测试里手抄百分号编错（抄错过一次）
    const header = 'attachment; filename="______-____.xlsx"; filename*=UTF-8\'\'' + encodeURIComponent(name);
    expect(filenameFromDisposition(header)).toBe(name);
  });

  it("没有 filename* 时退回 filename=", () => {
    expect(filenameFromDisposition('attachment; filename="export.xlsx"')).toBe("export.xlsx");
  });

  it("拿不到名字时返回 null，由调用方兜底", () => {
    expect(filenameFromDisposition(null)).toBeNull();
    expect(filenameFromDisposition("attachment")).toBeNull();
  });

  it("filename* 编码坏掉时也返回 null，而不是抛出中断下载", () => {
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%E6%9F%")).toBeNull();
  });
});