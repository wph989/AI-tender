/** LLM 管理 API 客户端。 */

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

import { sendJson } from "@/lib/api/request";

const BASE = "/api/v1/llm";

export async function listProviders(): Promise<LlmProvider[]> {
  const data = await sendJson<{ items: LlmProvider[] }>(BASE + "/providers", "GET");
  return data.items;
}

export function createProvider(input: ProviderInput): Promise<LlmProvider> {
  return sendJson<LlmProvider>(BASE + "/providers", "POST", input);
}

export function updateProvider(
  id: number,
  input: ProviderPatchInput,
): Promise<LlmProvider> {
  return sendJson<LlmProvider>(BASE + "/providers/" + id, "PATCH", input);
}

export async function deleteProvider(id: number): Promise<void> {
  await sendJson<unknown>(BASE + "/providers/" + id, "DELETE");
}

export function testProvider(id: number): Promise<LlmTestResult> {
  return sendJson<LlmTestResult>(BASE + "/providers/" + id + "/test", "POST", {});
}

export async function listRemoteModels(id: number): Promise<string[]> {
  const data = await sendJson<{ items: string[] }>(
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
  const data = await sendJson<{ imported: number }>(
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
  const data = await sendJson<{ items: LlmModel[] }>(url, "GET");
  return data.items;
}

export function createModel(input: ModelInput): Promise<LlmModel> {
  return sendJson<LlmModel>(BASE + "/models", "POST", input);
}

export function updateModel(
  id: number,
  input: ModelPatchInput,
): Promise<LlmModel> {
  return sendJson<LlmModel>(BASE + "/models/" + id, "PATCH", input);
}

export async function deleteModel(id: number): Promise<void> {
  await sendJson<unknown>(BASE + "/models/" + id, "DELETE");
}

export function testModel(id: number): Promise<LlmTestResult> {
  return sendJson<LlmTestResult>(BASE + "/models/" + id + "/test", "POST", {});
}

export async function listFeatures(): Promise<LlmFeature[]> {
  const data = await sendJson<{ items: LlmFeature[] }>(BASE + "/features", "GET");
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
  return sendJson<LlmFeature>(
    BASE + "/features/" + encodeURIComponent(key) + "/models",
    "PUT",
    { model_ids: modelIds, ...policy },
  );
}

export function getLlmSettings(): Promise<LlmSettings> {
  return sendJson(BASE + "/settings", "GET");
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
  return sendJson(BASE + "/calls?" + query, "GET");
}

export function startModelTest(
  id: number,
  capability: string,
): Promise<{ test_id: number; status: string }> {
  return sendJson(BASE + "/models/" + id + "/tests", "POST", { capability });
}
