"use client";

import { capabilityLabel } from "@/lib/llm/format";
import type { AdapterProfile, ModelParameterValue } from "@/types/llm";
import {
  FORM_LABEL_CLASS,
  FORM_ROW_CLASS,
  INPUT_CLASS,
  SELECT_CLASS,
} from "./ui";

export interface ModelConfiguration {
  capabilities: string[];
  supported: string[];
  values: Record<string, ModelParameterValue>;
}

export function defaultConfiguration(
  profile?: AdapterProfile,
): ModelConfiguration {
  return {
    capabilities: profile?.default_capabilities ?? [],
    supported: profile?.parameters ?? [],
    values: {},
  };
}

/** 新建、编辑和目录导入共用受控字段，避免三个入口对能力作不同的假设。 */
export function ModelConfigurationFields({
  profile,
  value,
  onChange,
}: {
  profile: AdapterProfile;
  value: ModelConfiguration;
  onChange: (next: ModelConfiguration) => void;
}) {
  const update = (key: string, next: ModelParameterValue | undefined) => {
    const values = { ...value.values };
    if (next === undefined) delete values[key];
    else values[key] = next;
    onChange({ ...value, values });
  };
  return (
    <div className="min-w-0 space-y-4">
      <div className={FORM_ROW_CLASS}>
        <span className={FORM_LABEL_CLASS}>允许能力</span>
        <div className="space-y-2">
          <div className="flex flex-wrap gap-3">
            {profile.capabilities.map((capability) => (
              <label
                key={capability}
                className="flex items-center gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  checked={value.capabilities.includes(capability)}
                  disabled={profile.required_capabilities.includes(capability)}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      capabilities: e.target.checked
                        ? [...value.capabilities, capability]
                        : value.capabilities.filter((c) => c !== capability),
                    })
                  }
                />
                {capabilityLabel[capability] ?? capability}
              </label>
            ))}
          </div>
          {profile.kind === "embedding" && (
            <p className="text-xs text-slate-500">
              {value.capabilities.includes("image_input")
                ? "文本＋图片多模态嵌入；图文能力需要单独测试。"
                : "纯文本嵌入；文本测试不能证明图片嵌入能力。"}
              {!profile.capabilities.includes("image_input") &&
                " 此接口尚不支持图片嵌入。"}
            </p>
          )}
          <p className="text-xs text-slate-500">
            按模型实际能力确认，目录和模型名称不构成能力证明。
          </p>
        </div>
      </div>
      <details className="rounded-lg border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer text-sm font-medium">
          本模型支持的参数（{value.supported.length} 项）
        </summary>
        <p className="my-2 text-xs text-slate-500">
          取消模型不接受的参数。留空使用服务默认值，保存时不会发送未填写的可选参数。
        </p>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {profile.parameters.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.supported.includes(key)}
                onChange={(e) => {
                  const values = { ...value.values };
                  if (!e.target.checked) delete values[key];
                  onChange({
                    ...value,
                    values,
                    supported: e.target.checked
                      ? [...value.supported, key]
                      : value.supported.filter((k) => k !== key),
                  });
                }}
              />
              {profile.parameter_schema[key]?.label ?? key}
            </label>
          ))}
        </div>
      </details>
      {profile.parameters
        .filter((key) => value.supported.includes(key))
        .map((key) => {
          const rule = profile.parameter_schema[key];
          if (!rule) return null;
          const current = value.values[key];
          return (
            <label className={FORM_ROW_CLASS} key={key}>
              <span className={FORM_LABEL_CLASS}>{rule.label}</span>
              {rule.type === "enum" ? (
                <select
                  className={SELECT_CLASS}
                  value={String(current ?? "")}
                  onChange={(e) => update(key, e.target.value || undefined)}
                >
                  <option value="">服务默认</option>
                  {rule.values?.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              ) : rule.type === "string_array" ? (
                <textarea
                  className={INPUT_CLASS}
                  rows={2}
                  value={Array.isArray(current) ? current.join("\n") : ""}
                  placeholder="留空不发送停止词"
                  onChange={(e) =>
                    update(
                      key,
                      e.target.value ? e.target.value.split("\n") : undefined,
                    )
                  }
                />
              ) : (
                <input
                  className={INPUT_CLASS}
                  type="number"
                  min={rule.min}
                  max={rule.max}
                  step={rule.type === "integer" ? 1 : "any"}
                  value={String(current ?? "")}
                  placeholder="服务默认"
                  onChange={(e) =>
                    update(
                      key,
                      e.target.value === ""
                        ? undefined
                        : Number(e.target.value),
                    )
                  }
                />
              )}
            </label>
          );
        })}
    </div>
  );
}
