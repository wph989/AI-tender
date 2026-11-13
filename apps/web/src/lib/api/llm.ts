/**
 * LLM 管理 API 客户端（设计文档 12 第 7 节，前缀 `/api/v1/llm`）。
 *
 * 为什么不并入 lib/api/client.ts：那个模块围着工作台取数转，两件事混在一起后
 * 改模型管理会牵动工作台的请求路径；错误解析这一段刻意重复，就是为了让两边互不影响。
 */

import type {
  LlmFeature,
  LlmSettings,
  LlmCall,
  AdapterProfile,
  LlmModel,
  LlmProvider,
  LlmTestResult,
  ModelInput,
  ModelPatchInput,
  ProviderInput,
  ProviderPatchInput,
} from "@/types/llm";

const BASE = "/api/v1/llm";

async function readError(response: Response, fallback: string): Promise<Error> {
  let message = fallback + " 返回 " + response.status;
  try {
    const payload: unknown = await response.json();
    if (
      typeof payload === "object" &&
      payload !== null &&
      "error" in payload &&
      typeof payload.error === "object" &&
      payload.error !== null &&
      "message" in payload.error &&
      typeof payload.error.message === "string"
    ) {
      message = payload.error.message;
    }
  } catch {
    // 网关可能返回非 JSON 错误页，保留 HTTP 状态作为可诊断信息。
  }
  return new Error(message);
}

/** GET 无请求体，其余方法带 JSON 体；DELETE 的成功响应也是 JSON，所以统一解析。 */
async function send<T>(
  url: string,
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  body?: unknown,
): Promise<T> {
  const init: RequestInit =
    body === undefined
      ? { method }
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        };
  const response = await fetch(url, init);
  if (!response.ok) throw await readError(response, "操作失败：" + url);
  return (await response.json()) as T;
}

export async function listProviders(): Promise<LlmProvider[]> {
  const data = await send<{ items: LlmProvider[] }>(BASE + "/providers", "GET");
  return data.items;
}

export function createProvider(input: ProviderInput): Promise<LlmProvider> {
  return send<LlmProvider>(BASE + "/providers", "POST", input);
}

export function updateProvider(
  id: number,
  input: ProviderPatchInput,
): Promise<LlmProvider> {
  return send<LlmProvider>(BASE + "/providers/" + id, "PATCH", input);
}

export async function deleteProvider(id: number): Promise<void> {
  await send<unknown>(BASE + "/providers/" + id, "DELETE");
}

export function testProvider(id: number): Promise<LlmTestResult> {
  return send<LlmTestResult>(BASE + "/providers/" + id + "/test", "POST", {});
}

export async function listRemoteModels(id: number): Promise<string[]> {
  const data = await send<{ items: string[] }>(
    BASE + "/providers/" + id + "/remote-models",
    "GET",
  );
  return data.items;
}

export async function importModels(
  id: number,
  modelIds: string[],
  profile: AdapterProfile,
  configuration?: Pick<
    ModelInput,
    | "capabilities"
    | "parameters"
    | "supported_parameters"
    | "temperature"
    | "max_tokens"
  >,
): Promise<number> {
  const data = await send<{ imported: number }>(
    BASE + "/providers/" + id + "/models/import",
    "POST",
    {
      model_ids: modelIds,
      kind: profile.kind,
      api_mode: profile.api_mode,
      capabilities: profile.default_capabilities,
      ...configuration,
    },
  );
  return data.imported;
}

export async function listModels(providerId?: number): Promise<LlmModel[]> {
  const url =
    providerId === undefined
      ? BASE + "/models"
      : BASE + "/models?provider_id=" + providerId;
  const data = await send<{ items: LlmModel[] }>(url, "GET");
  return data.items;
}

export function createModel(input: ModelInput): Promise<LlmModel> {
  return send<LlmModel>(BASE + "/models", "POST", input);
}

export function updateModel(
  id: number,
  input: ModelPatchInput,
): Promise<LlmModel> {
  return send<LlmModel>(BASE + "/models/" + id, "PATCH", input);
}

export async function deleteModel(id: number): Promise<void> {
  await send<unknown>(BASE + "/models/" + id, "DELETE");
}

export function testModel(id: number): Promise<LlmTestResult> {
  return send<LlmTestResult>(BASE + "/models/" + id + "/test", "POST", {});
}

export async function listFeatures(): Promise<LlmFeature[]> {
  const data = await send<{ items: LlmFeature[] }>(BASE + "/features", "GET");
  return data.items;
}

export function replaceBindings(
  key: string,
  modelIds: number[],
  policy: {
    revision: number;
    failover_limit: number;
    max_total_requests: number;
    },
): Promise<LlmFeature> {
  return send<LlmFeature>(
    BASE + "/features/" + encodeURIComponent(key) + "/models",
    "PUT",
    { model_ids: modelIds, ...policy },
  );
}

export function getLlmSettings(): Promise<LlmSettings> {
  return send(BASE + "/settings", "GET");
}
export function listCalls(filters: {
  feature_key?: string;
  model_id?: string;
  status?: string;
  invocation_id?: string;
  offset: number;
}): Promise<{ total: number; items: LlmCall[] }> {
  const query = new URLSearchParams({
    limit: "25",
    offset: String(filters.offset),
  });
  for (const key of [
    "feature_key",
    "model_id",
    "status",
    "invocation_id",
  ] as const)
    if (filters[key]) query.set(key, filters[key]);
  return send(BASE + "/calls?" + query, "GET");
}

export function startModelTest(
  id: number,
  capability: string,
): Promise<{ test_id: number; status: string }> {
  return send(BASE + "/models/" + id + "/tests", "POST", { capability });
}
