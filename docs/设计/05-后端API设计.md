# 后端API契约

接口响应由Pydantic模型声明，OpenAPI为前端线格式类型来源。`scripts/generate-api-types.py` 生成 `apps/web/src/types/api.generated.ts`；`--check` 拒绝漂移。

## 当前接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/healthz` | Health |
| `GET` | `/api/v1/readyz` | Readiness |
| `POST` | `/api/v1/projects` | Create Project |
| `GET` | `/api/v1/projects` | List Projects |
| `GET` | `/api/v1/projects/{project_id}` | Get Project |
| `PATCH` | `/api/v1/projects/{project_id}` | Patch Project |
| `DELETE` | `/api/v1/projects/{project_id}` | Delete Project |
| `POST` | `/api/v1/projects/{project_id}/files` | Upload Files |
| `PATCH` | `/api/v1/projects/{project_id}/files/{file_id}` | Patch File |
| `DELETE` | `/api/v1/projects/{project_id}/files/{file_id}` | Delete File |
| `POST` | `/api/v1/projects/{project_id}/files/{file_id}/replace` | Replace File |
| `GET` | `/api/v1/projects/{project_id}/files/{file_id}/original` | Get Original |
| `GET` | `/api/v1/versions/{version_id}/file` | Get Pdf |
| `GET` | `/api/v1/versions/{version_id}/original` | Get Original |
| `GET` | `/api/v1/versions/{version_id}/pages` | Get Pages |
| `GET` | `/api/v1/versions/{version_id}/elements` | Get Elements |
| `GET` | `/api/v1/versions/{version_id}/pages/{page_no}/elements` | Get Page Elements |
| `GET` | `/api/v1/versions/{version_id}/anchors/{anchor}` | Resolve Anchor |
| `GET` | `/api/v1/versions/{version_id}` | Get Version |
| `GET` | `/api/v1/versions/{version_id}/outline` | Get Outline |
| `POST` | `/api/v1/versions/{version_id}/anchors/resolve` | Resolve Anchors |
| `POST` | `/api/v1/versions/{version_id}/parse` | Parse Version |
| `POST` | `/api/v1/versions/{version_id}/reparse` | Reparse Version |
| `GET` | `/api/v1/jobs/{job_id}` | Get Job |
| `GET` | `/api/v1/jobs/{job_id}/events` | Job Events |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Cancel Job |
| `GET` | `/api/v1/llm/settings` | Llm Settings |
| `GET` | `/api/v1/llm/tests` | List Tests |
| `GET` | `/api/v1/llm/tests/{test_id}` | Get Test |
| `GET` | `/api/v1/llm/tests/{test_id}/preview` | Test Preview |
| `GET` | `/api/v1/llm/providers` | List Providers |
| `POST` | `/api/v1/llm/providers` | Create Provider |
| `PATCH` | `/api/v1/llm/providers/{provider_id}` | Update Provider |
| `DELETE` | `/api/v1/llm/providers/{provider_id}` | Delete Provider |
| `POST` | `/api/v1/llm/providers/{provider_id}/test` | Test Provider |
| `GET` | `/api/v1/llm/providers/{provider_id}/remote-models` | Remote Models |
| `POST` | `/api/v1/llm/providers/{provider_id}/models/import` | Import Models |
| `GET` | `/api/v1/llm/models` | List Models |
| `POST` | `/api/v1/llm/models` | Create Model |
| `PATCH` | `/api/v1/llm/models/{model_id}` | Update Model |
| `DELETE` | `/api/v1/llm/models/{model_id}` | Delete Model |
| `POST` | `/api/v1/llm/models/{model_id}/test` | Test Model |
| `POST` | `/api/v1/llm/models/{model_id}/tests` | Start Model Test |
| `GET` | `/api/v1/llm/features` | List Features |
| `PATCH` | `/api/v1/llm/features/{feature_key}` | Update Feature |
| `PUT` | `/api/v1/llm/features/{feature_key}/models` | Replace Bindings |
| `GET` | `/api/v1/llm/calls` | List Calls |
| `GET` | `/api/v1/config/items` | List Items |
| `GET` | `/api/v1/config/releases` | List Releases |
| `POST` | `/api/v1/config/releases` | Create Release |
| `GET` | `/api/v1/config/releases/{release_id}` | Get Release |
| `POST` | `/api/v1/config/releases/{release_id}/acknowledge` | Acknowledge Release |
| `POST` | `/api/v1/config/releases/{release_id}/activate` | Activate Release |
| `POST` | `/api/v1/config/releases/{release_id}/rollback` | Rollback Release |
| `GET` | `/api/v1/config/audit` | List Audit |
| `GET` | `/api/v1/knowledge/collections` | List Collections |
| `POST` | `/api/v1/knowledge/collections` | Create Collection |
| `GET` | `/api/v1/knowledge/collections/{collection_id}` | Get Collection |
| `PATCH` | `/api/v1/knowledge/collections/{collection_id}` | Update Collection |
| `DELETE` | `/api/v1/knowledge/collections/{collection_id}` | Delete Collection |
| `POST` | `/api/v1/knowledge/collections/{collection_id}/reindex` | Reindex Collection |
| `GET` | `/api/v1/knowledge/collections/{collection_id}/search` | Search Collection |
| `POST` | `/api/v1/knowledge/citations/resolve` | Resolve Citation |
| `POST` | `/api/v1/knowledge/embedding/test` | Test Embedding |
| `POST` | `/api/v1/knowledge/sources/{source_id}/process` | Process Source |
| `GET` | `/api/v1/projects/{project_id}/knowledge` | Project Knowledge |
| `PUT` | `/api/v1/projects/{project_id}/knowledge/collections` | Link Collections |
| `POST` | `/api/v1/knowledge/collections/{collection_id}/ask` | Ask Collection |
| `POST` | `/api/v1/projects/{project_id}/knowledge/ask` | Ask Project |
| `GET` | `/api/v1/knowledge/answers/{answer_id}` | Get Answer |
| `GET` | `/api/v1/projects/{project_id}/analysis` | Analysis Status |
| `POST` | `/api/v1/projects/{project_id}/analysis` | Start Analysis |
| `PUT` | `/api/v1/projects/{project_id}/analysis/settings` | Save Settings |
| `GET` | `/api/v1/analysis/reports/{report_id}` | Get Report |
| `GET` | `/api/v1/analysis/reports/{report_id}/modules/{module_key}/records` | Get Module Records |
| `POST` | `/api/v1/analysis/reports/{report_id}/records` | Get Report Records |
| `GET` | `/api/v1/analysis/reports/{report_id}/data` | Get Analysis Data |
| `POST` | `/api/v1/analysis/reports/{report_id}/context` | Get Analysis Context |
| `POST` | `/api/v1/analysis/reports/{report_id}/cancel` | Cancel Report |
| `GET` | `/api/v1/analysis/reports/{report_id}/runs/{run_id}/events` | Run Events |
| `POST` | `/api/v1/analysis/reports/{report_id}/retry` | Retry Report |
| `POST` | `/api/v1/analysis/reports/{report_id}/reviews` | Review Record |

## 状态与错误

报告详情返回执行、质量与运行信息。单专题正文由 `/modules/{module_key}/records` 读取；分析页通过 `POST /analysis/reports/{report_id}/records` 合并读取全部专题，传入 `module_keys` 与上次成功读取的 `versions`。每次读取先按实时权限与版本核验引用，再对完整可见响应生成版本；未变化的专题只返回 `module_key/version`，变化时附带 `data`，单专题读取错误通过 `error` 返回。每批最多13个专题，整批失败时页面清除全部缓存正文和版本。报告执行、机器自查和人工裁定分别表达。协议与当前运行不匹配的报告读取或补跑返回 `runtime_retired`；工作区草稿与正式数据快照按不同生命周期维护。错误响应保留稳定代码和具体原因。

分析响应只序列化明确声明的字段。原始模块记录通过 `evidence_ids/content_evidence` 关联独立证据，范围保留 `lot_refs`；正式快照记录携带经过解析的 `lot_ids`、完整引用和人工裁定。正文、范围、来源身份、质量问题及运行计数均进入 OpenAPI，前端从生成类型派生展示状态。专题待办读取 `quality_issues`，跨专题汇总读取快照 `gaps`。 输出声明复用应用中的 `OutputSchema`，版本、分类和列约束只维护一份。

文件下载支持HTTP Range，原件与PDF通过同一存储端口读取。`/api/v1/healthz`为存活信号，`/api/v1/readyz`核对PostgreSQL、Redis与所选存储；外部模型和解析供应商不作为就绪门槛。
