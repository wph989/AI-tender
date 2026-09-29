/**
 * LLM 管理接口的线格式类型。字段名与后端 `/api/v1/llm` 响应逐字一致（snake_case）。
 *
 * 理由同 types/workbench.ts：改成 camelCase 后，后端一改字段名前端只会拿到 undefined，
 * 而不是编译期报错；镜像结构能让这种改动立刻暴露。
 */

/** 测试接口无论成败都返回 200，所以必须把 status/error 一起呈现，不能只看 HTTP 码。 */
export interface LlmTestResult {
  status: "ok" | "error";
  latency_ms: number;
  http_status: number | null;
  error: string | null;
}

export interface LlmProvider {
  id: number;
  name: string;
  base_url: string;
  api_key_hint: string | null;
  has_api_key: boolean;
  enabled: boolean;
  last_test_status: string | null;
  last_test_at: string | null;
  last_test_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface LlmModel {
  id: number;
  provider_id: number;
  provider_name: string | null;
  model_id: string;
  display_name: string;
  timeout_seconds: number;
  temperature: number | null;
  max_tokens: number | null;
  enabled: boolean;
  last_test_status: string | null;
  last_test_at: string | null;
  last_test_error: string | null;
  created_at: string;
  updated_at: string;
}

/** 功能绑定行：priority 只在这一层存在（设计文档 12 第 2 节）。 */
export interface LlmBinding {
  priority: number;
  model_row_id: number;
  model_id: string;
  display_name: string;
  enabled: boolean;
  provider_id: number;
  provider_name: string;
}

export interface LlmFeature {
  key: string;
  name: string;
  failover_limit: number;
  description: string;
  bindings: LlmBinding[];
}

export interface ProviderInput {
  name: string;
  base_url: string;
  api_key?: string;
  enabled?: boolean;
}

export interface ProviderPatchInput {
  name?: string;
  base_url?: string;
  /** 空串 = 清除已存密钥；不传 = 保持原值（见 api/llm.py 的 _store_key）。 */
  api_key?: string;
  enabled?: boolean;
}

export interface ModelInput {
  provider_id: number;
  model_id: string;
  display_name?: string;
  timeout_seconds?: number;
  temperature?: number;
  max_tokens?: number;
  enabled?: boolean;
}

export interface ModelPatchInput {
  display_name?: string;
  timeout_seconds?: number;
  temperature?: number;
  max_tokens?: number;
  enabled?: boolean;
}