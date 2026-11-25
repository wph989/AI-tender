import { afterEach, expect, it, vi } from "vitest";

import { ApiError, requestJson } from "@/lib/api/request";

afterEach(() => vi.unstubAllGlobals());

it.each([403, 503])("HTTP %s保留状态与服务端消息，供调用方区分永久和临时失败", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { message: "服务端错误原因" },
  }), { status })));
  const failure = await requestJson("/test").catch((error: unknown) => error);
  expect(failure).toBeInstanceOf(ApiError);
  expect(failure).toBeInstanceOf(Error);
  expect(failure).toMatchObject({ status, message: "服务端错误原因" });
});

it("非JSON网关错误仍保留HTTP状态和回退消息", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("gateway error", { status: 502 })));
  await expect(requestJson("/test", undefined, "读取失败"))
    .rejects.toMatchObject({ status: 502, message: "读取失败 返回 502" });
});

it("网络错误保留原异常，不伪造HTTP状态", async () => {
  const failure = new TypeError("Failed to fetch");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(failure));
  await expect(requestJson("/test")).rejects.toBe(failure);
});
