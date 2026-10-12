"use client";

import { Checkbox, Collapse, Form, Input, Select } from "antd";
import { capabilityLabel } from "@/lib/llm/format";
import type { AdapterProfile, ModelParameterValue } from "@/types/llm";

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

/** 三个入口共用后端能力规则，防止导入和手动创建采用不同的参数边界。 */
export function ModelConfigurationFields({
  profile,
  value,
  onChange,
  disabled = false,
}: {
  profile: AdapterProfile;
  value: ModelConfiguration;
  onChange: (next: ModelConfiguration) => void;
  disabled?: boolean;
}) {
  const update = (key: string, next: ModelParameterValue | undefined) => {
    const values = { ...value.values };
    if (next === undefined) delete values[key];
    else values[key] = next;
    onChange({ ...value, values });
  };
  return (
    <div className="min-w-0">
      <Form.Item label="允许能力">
        <Checkbox.Group
          value={value.capabilities}
          disabled={disabled}
          options={profile.capabilities.map((cap) => ({
            value: cap,
            label: capabilityLabel[cap] ?? cap,
            disabled: disabled || profile.required_capabilities.includes(cap),
          }))}
          onChange={(capabilities) => onChange({ ...value, capabilities })}
        />
        {profile.kind === "embedding" && (
          <p className="mt-2 text-xs text-slate-500">
            {value.capabilities.includes("image_input")
              ? "文本＋图片多模态嵌入；图文能力需单独测试。"
              : "纯文本嵌入；文本测试不能证明图片嵌入能力。"}
          </p>
        )}
      </Form.Item>
      <Collapse
        className="mb-4"
        items={[
          {
            key: "parameters",
            label: `本模型支持的参数（${value.supported.length} 项）`,
            children: (
              <>
                <p className="mb-3 text-xs text-slate-500">
                  取消模型不接受的参数。可选值留空时使用服务默认值。
                </p>
                <Checkbox.Group
                  value={value.supported}
                  disabled={disabled}
                  options={profile.parameters.map((key) => ({
                    value: key,
                    label: profile.parameter_schema[key]?.label ?? key,
                  }))}
                  onChange={(supported) =>
                    onChange({
                      ...value,
                      supported,
                      values: Object.fromEntries(
                        Object.entries(value.values).filter(([key]) =>
                          supported.includes(key),
                        ),
                      ),
                    })
                  }
                />
              </>
            ),
          },
        ]}
      />
      {profile.parameters
        .filter((key) => value.supported.includes(key))
        .map((key) => {
          const rule = profile.parameter_schema[key];
          if (!rule) return null;
          const current = value.values[key];
          return (
            <Form.Item label={rule.label} key={key}
              extra={key === "max_tokens" ? "实际输出取本项与任务输出预算的较小值；留空使用任务预算。" : undefined}>
              {rule.type === "enum" ? (
                <Select
                  aria-label={rule.label}
                  disabled={disabled}
                  value={String(current ?? "")}
                  onChange={(next) => update(key, next || undefined)}
                  options={[
                    { value: "", label: "服务默认" },
                    ...(rule.values ?? []).map((option) => ({
                      value: option,
                      label: option,
                    })),
                  ]}
                />
              ) : rule.type === "string_array" ? (
                <Input.TextArea
                  aria-label={rule.label}
                  disabled={disabled}
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
                <Input
                  aria-label={rule.label}
                  disabled={disabled}
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
            </Form.Item>
          );
        })}
    </div>
  );
}
