/**
 * 导出文件名的解析口径。
 *
 * 后端对中文名走 RFC 5987 的 filename*（见 api/storage.py 的 content_disposition），
 * 只读 filename= 会拿到被下划线替换过的名字——用户看到的文件名会变成 "______-____.xlsx"。
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { filenameFromDisposition, listProjects } from "@/lib/api/client";

afterEach(() => vi.unstubAllGlobals());

it("项目筛选覆盖后端所有分页，后续分页保留搜索条件", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 1 }, { id: 2 }], limit: 2 })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 3 }], limit: 2 })));
  vi.stubGlobal("fetch", fetchMock);
  expect((await listProjects("工程 A")).map((item) => item.id)).toEqual([1, 2, 3]);
  const query = new URL(String(fetchMock.mock.calls[1]?.[0]), "http://localhost").searchParams;
  expect(query.get("offset")).toBe("2");
  expect(query.get("keyword")).toBe("工程 A");
});

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
