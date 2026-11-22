/** 配置中心的前端类型（对齐后端 `tender/api/configuration/routes.py` 的响应）。 */

export type ConfigLayer = "L1" | "L2";

export type ConfigValueType = "int" | "number" | "bool" | "string" | "json" | "secret";

export interface ConfigItem {
  key: string;
  layer: ConfigLayer;
  value_type: ConfigValueType;
  description: string;
  requires_gate: boolean;
  default: unknown;
  value: unknown;
  overridden: boolean;
  writable: boolean;
  minimum?: number;
  maximum?: number;
  choices?: string[];
}

export interface ConfigItemsResponse {
  role: string;
  items: ConfigItem[];
  active: { release_id: number; version_no: number } | null;
}

export interface ConfigRelease {
  id: number;
  version_no: number;
  status: "draft" | "active" | "archived" | "rolled_back";
  note: string | null;
  created_by: string;
  created_at: string;
  based_on: number | null;
}

export interface ConfigChanged {
  old: unknown;
  new: unknown;
}

export interface ImpactEntry {
  kind: string;
  ref: string;
  acked: boolean;
}

export interface GateResult {
  passed: boolean;
  blockers: string[];
}

export interface ConfigAuditEntry {
  id: number;
  release_id: number;
  version_no: number;
  actor: string;
  action: string;
  diff: Record<string, unknown>;
  reason: string | null;
  created_at: string;
}

export interface ConfigReleaseDetail extends ConfigRelease {
  overrides: Record<string, unknown>;
  values: Record<string, unknown>;
  changed: Record<string, ConfigChanged>;
  impact: ImpactEntry[];
  gate: GateResult;
  audit: ConfigAuditEntry[];
}

export interface CreateReleaseResponse {
  id: number;
  version_no: number;
  status: "draft" | "active";
  changed: Record<string, ConfigChanged>;
  gated: string[];
  note: string | null;
}
