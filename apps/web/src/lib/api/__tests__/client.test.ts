/** 项目列表覆盖后端分页，避免筛选结果因只读首页而漏项。 */
import { afterEach, expect, it, vi } from "vitest";

import { listProjects } from "@/lib/api/client";

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
