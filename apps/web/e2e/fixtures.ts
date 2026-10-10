import type { Page } from "@playwright/test";

const date = "2026-10-10T10:00:00Z";
export const provider = {
  id: 1,
  name: "测试供应商",
  protocol: "openai_compatible",
  auth_mode: "api_key",
  revision: 3,
  base_url: "https://example.test/v1",
  has_api_key: true,
  api_key_hint: "****test",
  enabled: true,
  test_validity: "valid",
  last_test_error: null,
  last_test_at: date,
  created_at: date,
  updated_at: date,
};
export const profile = {
  protocol: "openai_compatible",
  kind: "language",
  api_mode: "chat_completions",
  capabilities: ["text_input", "json_output"],
  required_capabilities: ["text_input"],
  default_capabilities: ["text_input", "json_output"],
  parameters: ["temperature", "max_tokens"],
  parameter_schema: {
    temperature: { label: "温度", type: "number", min: 0, max: 2 },
    max_tokens: { label: "输出上限", type: "integer", min: 1, max: 100000 },
  },
  parameter_bounds: {},
  adapter_version: "test",
};
export const models = Array.from({ length: 20 }, (_, i) => ({
  id: i + 1,
  revision: 7,
  provider_id: 1,
  provider_name: provider.name,
  provider_enabled: true,
  model_id: `model-${i + 1}`,
  display_name: `测试模型 ${i + 1}`,
  kind: "language",
  api_mode: "chat_completions",
  capabilities: ["text_input", "json_output"],
  supported_parameters: ["temperature", "max_tokens"],
  parameters: {},
  embedding_input_type: null,
  timeout_seconds: 90,
  extra_retries: 1,
  temperature: 0.7,
  max_tokens: 8192,
  enabled: true,
  test_capabilities: ["text_input"],
  capability_tests: {},
  last_test_at: null,
  last_test_error: null,
}));
export const project = {
  id: 1,
  company_id: 1,
  name: "界面验收项目",
  project_no: "TEST-001",
  owner: "测试人员",
  status: "active",
  created_at: date,
  file_count: 1,
  review_count: 0,
  failed_count: 1,
  files: [
    {
      project_file_id: 1,
      project_id: 1,
      version_id: 1,
      role: "main",
      display_name: "招标文件.pdf",
      is_parseable: true,
      replaces_id: null,
      sort_no: 1,
      created_at: date,
      sha256: "abc",
      mime: "application/pdf",
      size_bytes: 100,
      page_count: 2,
      parse_status: "failed",
      parse_tier: "advanced",
      parse_ocr_mode: "ocr",
      latest_run_id: 1,
      replaced_by_id: null,
      extraction_count: 3,
      review_count: 0,
      confirmed_count: 3,
      extraction_status: "failed",
      latest_job: null,
    },
  ],
  lots: [],
};
export const collections = [
  {
    id: 1,
    name: "测试知识库",
    purpose: "company",
    is_project: false,
    upload_project_id: 1,
    file_count: 1,
    sources: [],
    embedding_configured: false,
  },
];
export const releases = Array.from({ length: 12 }, (_, i) => ({
  id: i + 1,
  version_no: i + 1,
  status: i === 0 ? "active" : "archived",
  note: `配置变更 ${i + 1}`,
  created_by: "测试人员",
  created_at: date,
  based_on: null,
}));
export const calls = Array.from({ length: 30 }, (_, i) => ({
  id: i + 1,
  invocation_id: "chain-1",
  feature_key: "extract",
  display_name: `请求模型 ${i + 1}`,
  provider_name: "测试供应商",
  purpose: "extract",
  status: "ok",
  latency_ms: 500,
  request_ordinal: i + 1,
  retry_ordinal: 0,
  candidate_ordinal: 1,
  prompt_tokens: 100,
  completion_tokens: 50,
  image_count: null,
  vector_count: null,
  document_count: null,
  error_message: null,
  created_at: date,
}));

/** 所有 API 均被拦截，回归测试不会修改业务数据库或调用真实模型。 */
export async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    const method = route.request().method();
    let body: unknown;
    if (path === "/llm/providers")
      body =
        method === "GET"
          ? { items: [provider] }
          : { ...provider, ...route.request().postDataJSON() };
    else if (/^\/llm\/providers\/\d+$/.test(path)) body = provider;
    else if (path === "/llm/providers/1/remote-models")
      body = { items: ["model-a", "model-b"] };
    else if (path === "/llm/models")
      body = method === "GET" ? { items: models } : { id: 100 };
    else if (/^\/llm\/models\/\d+$/.test(path)) body = models[0];
    else if (path === "/llm/features")
      body = {
        items: [
          {
            key: "extract",
            name: "字段抽取",
            required_kind: "language",
            revision: 1,
            bindings: [],
            failover_limit: 1,
            max_total_requests: 3,
            deadline_seconds: 120,
          },
        ],
      };
    else if (path === "/llm/settings")
      body = {
        secret_key_ready: true,
        adapter_profiles: [profile],
        test_valid_seconds: 3600,
      };
    else if (path === "/llm/calls") {
      const offset = Number(url.searchParams.get("offset"));
      body = { total: calls.length, items: calls.slice(offset, offset + 25) };
    } else if (path === "/projects")
      body =
        method === "GET"
          ? {
              items: Array.from({ length: 18 }, (_, i) => ({
                ...project,
                id: i + 1,
                name: `${project.name} ${i + 1}`,
              })),
            }
          : { ...project, ...route.request().postDataJSON() };
    else if (path === "/projects/1") body = project;
    else if (path === "/projects/1/analysis")
      body = {
        analysis_category: "goods",
        analysis_topics: [],
        lots: [],
        reports: [],
        sources: [],
        categories: { goods: "货物" },
        topics: {},
      };
    else if (path === "/projects/1/knowledge")
      body = { linked_collection_ids: [] };
    else if (path === "/knowledge/collections")
      body =
        method === "GET"
          ? { items: collections }
          : { ...collections[0], ...route.request().postDataJSON() };
    else if (path === "/knowledge/collections/1") body = collections[0];
    else if (path === "/config/items")
      body = {
        role: "admin",
        active: { release_id: 1, version_no: 1 },
        items: [
          {
            key: "analysis.max_inflight",
            value: 2,
            default: 2,
            layer: "L1",
            value_type: "int",
            description: "分析并发数",
            writable: true,
            overridden: false,
          },
        ],
      };
    else if (path === "/config/releases") body = { items: releases };
    else if (/^\/config\/releases\/\d+$/.test(path)) {
      const id = Number(path.split("/").at(-1));
      body = {
        ...releases[id - 1],
        changed: {},
        impact: [],
        gate: { passed: true, blockers: [], soft_breaches: [] },
        audit: [],
      };
    } else {
      await route.fulfill({
        status: 404,
        json: { error: { message: `未配置的测试接口：${method} ${path}` } },
      });
      return;
    }
    await route.fulfill({ json: body });
  });
}
