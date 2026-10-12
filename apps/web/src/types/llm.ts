/**
 * LLM 管理接口的线格式类型。字段名与后端 `/api/v1/llm` 响应逐字一致（snake_case）。
 *
 * 理由同 types/workbench.ts：改成 camelCase 后，后端一改字段名前端只会拿到 undefined，
 * 而不是编译期报错；镜像结构能让这种改动立刻暴露。
 */

/** 测试接口无论成败都返回 200，所以必须把 status/error 一起呈现，不能只看 HTTP 码。 */
export interface LlmTestResult {
  test_id: number;
  status: "ok" | "error" | "unsupported" | "unknown";
  latency_ms: number;
  http_status: number | null;
  error: string | null;
  image_count?: number | null;
  preview_url?: string | null;
  vector_count?: number | null;
  embedding_dimensions?: number | null;
  document_count?: number | null;
}

export interface LlmCallUsage {
  image_count: number | null;
  vector_count: number | null;
  document_count: number | null;
}

export type ModelKind =
  | "language"
  | "embedding"
  | "rerank"
  | "image_generation";
export type ModelParameterValue = number | string | string[];
export interface ParameterSchema {
  label: string;
  type: "number" | "integer" | "enum" | "string_array";
  min?: number;
  max?: number;
  values?: string[];
  max_items?: number;
}
export interface CapabilityTest {
  id: number;
  capability: string;
  status: string;
  validity: string;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  expires_at: string | null;
  result: Partial<LlmTestResult>;
}
export interface AdapterProfile {
  protocol: string;
  kind: ModelKind;
  api_mode: string;
  capabilities: string[];
  parameters: string[];
  required_capabilities: string[];
  default_capabilities: string[];
  parameter_schema: Record<string, ParameterSchema>;
  adapter_version: string;
  parameter_bounds: Record<string, { min: number; max?: number }>;
}
export interface LlmSettings {
  secret_key_ready: boolean;
  adapter_profiles: AdapterProfile[];
  test_valid_seconds: number;
  model_fields?: Record<string, ParameterSchema>;
  feature_fields?: Record<string, ParameterSchema>;
  max_bindings?: number;
}
export interface LlmCall extends LlmCallUsage {
  id: number;
  invocation_id: string | null;
  feature_key: string | null;
  display_name: string | null;
  provider_name: string | null;
  purpose: string;
  status: string;
  latency_ms: number;
  request_ordinal: number | null;
  retry_ordinal: number | null;
  candidate_ordinal: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  error_message: string | null;
  created_at: string;
}
export interface LlmProvider {
  protocol: string;
  auth_mode: "api_key" | "none";
  revision: number;
  test_validity: string;
  api_key_updated_at: string | null;
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
  kind: ModelKind;
  api_mode: string;
  capabilities: string[];
  extra_retries: number;
  revision: number;
  provider_enabled: boolean;
  test_validity: string;
  supported_parameters: string[];
  parameters: Record<string, ModelParameterValue>;
  embedding_input_type: "text" | "multimodal" | null;
  embedding_space_id: string | null;
  test_capabilities: string[];
  capability_tests: Record<string, CapabilityTest>;
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
  binding_available?: boolean;
  revision: number;
  max_total_requests: number;
  deadline_seconds: number;
  required_kind: ModelKind;
  key: string;
  name: string;
  failover_limit: number;
  description: string;
  bindings: LlmBinding[];
}

export interface ProviderInput {
  protocol?: string;
  auth_mode?: "api_key" | "none";
  name: string;
  base_url: string;
  api_key?: string;
  enabled?: boolean;
}

export interface ProviderPatchInput {
  revision?: number;
  auth_mode?: "api_key" | "none";
  clear_api_key?: boolean;
  name?: string;
  base_url?: string;
  /** 空串 = 清除已存密钥；不传 = 保持原值（见 api/llm.py 的 _store_key）。 */
  api_key?: string;
  enabled?: boolean;
}

export interface ModelInput {
  kind?: ModelKind;
  api_mode?: string;
  capabilities?: string[];
  extra_retries?: number;
  parameters?: Record<string, ModelParameterValue>;
  supported_parameters?: string[] | null;
  provider_id: number;
  model_id: string;
  display_name?: string;
  timeout_seconds?: number;
  temperature?: number | null;
  max_tokens?: number | null;
  enabled?: boolean;
}

export interface ModelPatchInput {
  revision?: number;
  kind?: ModelKind;
  api_mode?: string;
  capabilities?: string[];
  extra_retries?: number;
  parameters?: Record<string, ModelParameterValue>;
  supported_parameters?: string[] | null;
  display_name?: string;
  timeout_seconds?: number;
  temperature?: number | null;
  max_tokens?: number | null;
  enabled?: boolean;
}
