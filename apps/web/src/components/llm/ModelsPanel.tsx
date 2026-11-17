"use client";

import { useEffect, useState } from "react";
import {
  Alert,
  App,
  Button,
  Tag,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
} from "antd";
import { DataTable } from "@/components/DataTable";
import { useFeedback } from "@/hooks/useFeedback";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import {
  ModelConfigurationFields,
  defaultConfiguration,
  type ModelConfiguration,
} from "./ModelConfigurationFields";
import {
  createModel,
  deleteModel,
  startModelTest,
  updateModel,
} from "@/lib/api/llm";
import {
  formatTime,
  kindLabel,
  capabilityLabel,
  message,
  validityLabel,
  withinNumericRule,
} from "@/lib/llm/format";
import type {
  AdapterProfile,
  LlmModel,
  LlmProvider,
  ModelInput,
  ModelPatchInput,
  ModelKind,
  ParameterSchema,
} from "@/types/llm";

interface Props {
  providers: LlmProvider[];
  models: LlmModel[];
  profiles: AdapterProfile[];
  fields?: Record<string, ParameterSchema>;
  onChanged: () => Promise<void>;
}

export function ModelsPanel({ providers, models, profiles, fields = {}, onChanged }: Props) {
  const { modal, message: toast } = App.useApp();
  const [dirty, setDirty] = useState(false);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTests, setSelectedTests] = useState<Record<number, string>>(
    {},
  );
  const [embeddingType, setEmbeddingType] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [kind, setKind] = useState("");
  const [provider, setProvider] = useState("");
  const [state, setState] = useState("");
  useFeedback(error, notice);
  const closeEditor = useUnsavedChanges(dirty, busy);
  const edit = (id: number | "new") => {
    setDirty(false);
    setError(null);
    setEditing(id);
  };
  const run = async (task: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await task();
      await onChanged().catch(() =>
        setError("操作已完成，刷新列表失败，请点击刷新。"),
      );
    } catch (e) {
      setError(message(e, "操作失败"));
    } finally {
      setBusy(false);
    }
  };
  const save = (input: ModelInput | ModelPatchInput) =>
    void run(async () => {
      if (editing === "new") await createModel(input as ModelInput);
      else if (editing !== null) await updateModel(editing, input);
      setEditing(null);
      setDirty(false);
      void toast.success("模型已保存");
    });
  const hasRunningTests = models.some((model) =>
    Object.values(model.capability_tests).some(
      (test) => test.status === "running",
    ),
  );
  useEffect(() => {
    if (!hasRunningTests) return;
    // 刷新页面后继续读取持久测试，不重新发送请求；切走或测试结束时停止轮询。
    const timer = window.setInterval(() => {
      void onChanged().catch((e) => setError(message(e, "读取测试状态失败")));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [hasRunningTests, onChanged]);
  const test = async (model: LlmModel) => {
    await run(async () => {
      const capability =
        selectedTests[model.id] ??
        (model.embedding_input_type === "multimodal"
          ? "multimodal_embedding"
          : model.test_capabilities[0]);
      if (!capability) throw new Error("该模型没有可测试能力");
      const result = await startModelTest(model.id, capability);
      setNotice(
        `${model.display_name} 的${capabilityLabel[capability]}测试已受理（#${result.test_id}），结果将自动更新。`,
      );
    });
  };
  const visible = models.filter(
    (m) =>
      (!keyword ||
        (m.display_name + " " + m.model_id)
          .toLowerCase()
          .includes(keyword.toLowerCase())) &&
      (!kind || m.kind === kind) &&
      (!embeddingType || m.embedding_input_type === embeddingType) &&
      (!provider || String(m.provider_id) === provider) &&
      (!state ||
        (state === "enabled"
          ? m.enabled && m.provider_enabled
          : !m.enabled || !m.provider_enabled)),
  );
  return (
    <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-[19px] font-semibold">模型</h2>
          <p className="mt-1 text-sm text-slate-500">
            按能力配置并测试。测试会发送一次真实请求，可能产生费用，不会自动重试或切换模型。
          </p>
        </div>
        <Button
          type="primary"
          htmlType="submit"

          disabled={busy || editing !== null || !providers.length}
          onClick={() => edit("new")}
        >
          新增模型
        </Button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        四类模型按接口声明能力；视觉和图文嵌入单独测试。测试图片只供临时预览。
      </p>
      {hasRunningTests && (
        <p role="status" className="mt-3 text-sm text-slate-500">
          测试进行中，刷新页面可继续查看。本地模型首次加载可能较慢。
        </p>
      )}
      {notice && (
        <p role="status" className="mt-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}
      <div className="my-4 flex flex-wrap gap-2">
        <Input.Search
          aria-label="搜索模型"
          placeholder="搜索模型名称或 ID"
          allowClear
          style={{ width: 240, maxWidth: "100%" }}
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value);
            setPage(1);
          }}
        />
        <Select
          aria-label="按模型种类筛选"
          value={kind}
          onChange={(v) => {
            setKind(v);
            setPage(1);
          }}
          options={[
            { value: "", label: "全部种类" },
            ...Object.entries(kindLabel).map(([value, label]) => ({
              value,
              label,
            })),
          ]}
        />
        <Select
          aria-label="按嵌入输入类型筛选"
          value={embeddingType}
          onChange={(v) => {
            setEmbeddingType(v);
            setPage(1);
          }}
          options={[
            { value: "", label: "全部输入类型" },
            { value: "text", label: "纯文本嵌入" },
            { value: "multimodal", label: "文本＋图片嵌入" },
          ]}
        />
        <Select
          aria-label="按供应商筛选"
          value={provider}
          onChange={(v) => {
            setProvider(v);
            setPage(1);
          }}
          options={[
            { value: "", label: "全部供应商" },
            ...providers.map((p) => ({ value: String(p.id), label: p.name })),
          ]}
        />
        <Select
          aria-label="按模型状态筛选"
          value={state}
          onChange={(v) => {
            setState(v);
            setPage(1);
          }}
          options={[
            { value: "", label: "全部状态" },
            { value: "enabled", label: "已启用" },
            { value: "disabled", label: "模型或供应商停用" },
          ]}
        />
      </div>
      {!providers.length && (
        <Alert
          type="info"
          showIcon
          title="请先在「连接供应商」中添加供应商，再创建模型。"
        />
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-rose-700">
          {error}
        </p>
      )}
      <Modal
        open={editing !== null}
        title={editing === "new" ? "新增模型" : "编辑模型"}
        width={720}
        centered
        destroyOnHidden
        mask={{ closable: false }}
        keyboard={!busy}
        closable={!busy}
        className="editor-modal"
        onCancel={() => closeEditor(() => { setEditing(null); setDirty(false); setError(null); })}
        footer={
          <Space>
            <Button
              disabled={busy}
              onClick={() => closeEditor(() => { setEditing(null); setDirty(false); setError(null); })}
            >
              取消
            </Button>
            <Button
              type="primary"
              htmlType="submit"
              form="model-form"
              loading={busy}
            >
              保存
            </Button>
          </Space>
        }
      >
        {error && (
          <Alert className="mb-4" type="error" showIcon title={error} />
        )}
        {editing !== null && (
          <ModelForm
            key={editing}
            providers={providers}
            model={models.find((m) => m.id === editing) ?? null}
            profiles={profiles}
            fields={fields}
            busy={busy}
            onSubmit={save}
            onDirty={() => setDirty(true)}
          />
        )}
      </Modal>
      <DataTable<LlmModel>
        rowKey="id"
        className="mt-4"
        dataSource={visible}
        scroll={{ x: 1100 }}
        pagination={{
          current: Math.min(page, Math.max(1, Math.ceil(visible.length / 10))),
          pageSize: 10,
          onChange: setPage,
        }}
        locale={{
          emptyText: "暂无符合条件的模型，可手动添加或从供应商目录导入。",
        }}
        expandable={{
          columnTitle: "详情",
          columnWidth: 56,
          expandedRowRender: (model) => (
            <div className="model-details">
              <p className="mt-3 text-sm text-slate-600">
                {model.api_mode} ·{" "}
                {model.kind === "language" ? "响应间隔" : "超时"}{" "}
                {model.timeout_seconds}s
                {model.kind === "language" &&
                  ` · 单次总时限 ${
                    model.total_timeout_seconds == null
                      ? "不限制"
                      : `${model.total_timeout_seconds}s`
                  }`}
                {" · 失败后额外重试 "}
                {model.extra_retries} 次
              </p>
              {model.kind === "language" && (
                <p className="mt-1 text-xs text-slate-500">
                  温度 {model.temperature ?? "服务默认"} · 输出上限{" "}
                  {model.max_tokens ?? "服务默认"}
                </p>
              )}
              <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                {model.test_capabilities.map((capability) => {
                  const check = model.capability_tests[capability];
                  return (
                    <div key={capability} className="text-xs text-slate-600">
                      <span className="font-medium">
                        {capabilityLabel[capability]}
                      </span>{" "}
                      · {validityLabel(check?.validity ?? "untested")}
                      {check?.latency_ms != null &&
                        ` · ${(check.latency_ms / 1000).toFixed(1)} 秒`}
                      {check?.result.vector_count != null &&
                        ` · ${check.result.vector_count} 条 ${check.result.embedding_dimensions} 维向量`}
                      {check?.error_message && (
                        <p className="mt-1 text-rose-700">
                          {check.error_message}
                        </p>
                      )}
                      {check?.validity === "valid" &&
                        check.result.preview_url && (
                          <figure className="mt-2">
                            {/* 预览来自本项目后端，禁止浏览器直接访问供应商图片地址。 */}
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={check.result.preview_url}
                              alt="本次生图测试预览"
                              className="max-h-64 max-w-full rounded-lg border border-slate-200"
                            />
                            <figcaption className="mt-1">
                              临时测试图片，有效至{" "}
                              {formatTime(check.expires_at)}。
                            </figcaption>
                          </figure>
                        )}
                    </div>
                  );
                })}
              </div>
              {model.last_test_error &&
                Object.keys(model.capability_tests).length === 0 && (
                  <p className="mt-2 text-sm text-rose-700">
                    {model.last_test_error}
                  </p>
                )}
            </div>
          ),
        }}
        columns={[
          {
            title: "模型 / 供应商",
            key: "model",
            width: 260,
            render: (_, model) => (
              <div>
                <strong className="table-title">{model.display_name}</strong>
                <div className="table-meta">
                  {model.provider_name} · {model.model_id}
                </div>
              </div>
            ),
          },
          {
            title: "类型",
            key: "kind",
            width: 130,
            render: (_, model) => (
              <Tag>
                {kindLabel[model.kind]}
                {model.embedding_input_type === "multimodal"
                  ? " · 图文"
                  : model.capabilities.includes("image_input")
                    ? " · 视觉"
                    : ""}
              </Tag>
            ),
          },
          {
            title: "状态 / 最近测试",
            key: "status",
            width: 180,
            render: (_, model) => (
              <div>
                <Tag
                  color={
                    !model.provider_enabled || !model.enabled
                      ? "default"
                      : "success"
                  }
                >
                  {!model.provider_enabled
                    ? "供应商停用"
                    : model.enabled
                      ? "已启用"
                      : "已停用"}
                </Tag>
                {Object.values(model.capability_tests).some(
                  (check) => check.status === "running",
                ) && <Tag color="processing">测试中</Tag>}
                {(model.last_test_error ||
                  Object.values(model.capability_tests).some(
                    (check) => check.error_message,
                  )) && <Tag color="error">测试异常 · 展开详情</Tag>}
                <div className="table-meta">
                  {formatTime(model.last_test_at)}
                </div>
              </div>
            ),
          },
          {
            title: "操作",
            key: "actions",
            fixed: "right",
            width: 420,
            render: (_, model) => (
              <div className="model-row-actions">
                <Switch
                  aria-label={`${model.display_name}启用状态`}
                  checked={model.enabled}
                  checkedChildren="启用"
                  unCheckedChildren="停用"
                  disabled={busy || editing !== null}
                  onChange={(enabled) =>
                    void run(async () => {
                      await updateModel(model.id, {
                        enabled,
                        revision: model.revision,
                      });
                      void toast.success(`模型已${enabled ? "启用" : "停用"}`);
                    })
                  }
                />
                <Select
                  aria-label={`${model.display_name} 测试能力`}
                  value={
                    selectedTests[model.id] ??
                    (model.embedding_input_type === "multimodal"
                      ? "multimodal_embedding"
                      : model.test_capabilities[0])
                  }
                  onChange={(value) =>
                    setSelectedTests((old) => ({ ...old, [model.id]: value }))
                  }
                  disabled={busy}
                  options={model.test_capabilities.map((value) => ({
                    value,
                    label: capabilityLabel[value],
                  }))}
                />
                <Button
                  disabled={
                    busy ||
                    Object.values(model.capability_tests).some(
                      (check) => check.status === "running",
                    )
                  }
                  onClick={() => void test(model)}
                >
                  {Object.values(model.capability_tests).some(
                    (check) => check.status === "running",
                  )
                    ? "测试中…"
                    : "测试"}
                </Button>
                <Button
                  disabled={busy || editing !== null}
                  onClick={() => edit(model.id)}
                >
                  编辑
                </Button>
                <Button
                  danger
                  disabled={busy}
                  onClick={() =>
                    modal.confirm({
                      title: `删除模型「${model.display_name}」？`,
                      content: "有效绑定或索引引用会阻止删除。",
                      okText: "删除",
                      okButtonProps: { danger: true },
                      onOk: async () => {
                        try {
                          await deleteModel(model.id);
                          void toast.success("模型已删除");
                          await onChanged().catch(() =>
                            setError("模型已删除，刷新失败。"),
                          );
                        } catch (caught) {
                          setError(message(caught, "删除模型失败"));
                          throw caught;
                        }
                      },
                    })
                  }
                >
                  删除
                </Button>
              </div>
            ),
          },
        ]}
      />
    </section>
  );
}

function ModelForm({
  providers,
  model,
  profiles,
  fields,
  busy,
  onSubmit,
  onDirty,
}: {
  providers: LlmProvider[];
  model: LlmModel | null;
  profiles: AdapterProfile[];
  fields: Record<string, ParameterSchema>;
  busy: boolean;
  onSubmit: (input: ModelInput | ModelPatchInput) => void;
  onDirty: () => void;
}) {
  const [form] = Form.useForm();
  const [revision] = useState(model?.revision);
  const [providerId, setProviderId] = useState(
    model?.provider_id ?? providers[0]?.id ?? 0,
  );
  const available = profiles.filter(
    (p) => p.protocol === providers.find((v) => v.id === providerId)?.protocol,
  );
  const initial = available.find(
    (p) => !model || (p.kind === model.kind && p.api_mode === model.api_mode),
  );
  const [kind, setKind] = useState<ModelKind>(
    model?.kind ?? initial?.kind ?? "language",
  );
  const [mode, setMode] = useState(model?.api_mode ?? initial?.api_mode ?? "");
  const selected = available.find(
    (p) => p.kind === kind && p.api_mode === mode,
  );
  const [configuration, setConfiguration] = useState<ModelConfiguration>(() =>
    model
      ? {
          capabilities: model.capabilities,
          supported: model.supported_parameters,
          values: {
            ...model.parameters,
            ...(model.temperature != null
              ? { temperature: model.temperature }
              : {}),
            ...(model.max_tokens != null
              ? { max_tokens: model.max_tokens }
              : {}),
          },
        }
      : defaultConfiguration(initial),
  );
  const choose = (p?: AdapterProfile) => {
    if (!model && p?.kind !== kind) {
      form.setFieldValue("timeout_seconds", p?.kind === "language" ? 10 : 90);
    }
    setMode(p?.api_mode ?? "");
    form.setFieldValue("api_mode", p?.api_mode);
    setConfiguration(defaultConfiguration(p));
    onDirty();
  };
  return (
    <Form
      form={form}
      id="model-form"
      layout="vertical"
      disabled={busy}
      onValuesChange={onDirty}
      scrollToFirstError={{ focus: true }}
      initialValues={{
        api_mode: mode,
        model_id: model?.model_id ?? "",
        display_name: model?.display_name ?? "",
        timeout_seconds: model?.timeout_seconds ?? (kind === "language" ? 10 : 90),
        total_timeout_seconds: model?.total_timeout_seconds ?? null,
        extra_retries: model?.extra_retries ?? 1,
      }}
      onFinish={(values) => {
        if (!selected) return;
        // 空值明确发送 null，才能清除编辑前的可选参数；版本号保持打开时的快照。
        // 启停由列表单独修改，编辑配置不回写打开表单时的启停状态。
        const input = {
          display_name: values.display_name?.trim() || values.model_id.trim(),
          kind: selected.kind,
          api_mode: selected.api_mode,
          capabilities: configuration.capabilities,
          supported_parameters: configuration.supported,
          parameters: Object.fromEntries(
            Object.entries(configuration.values).filter(
              ([key]) => !["temperature", "max_tokens"].includes(key),
            ),
          ),
          timeout_seconds: values.timeout_seconds,
          total_timeout_seconds: selected.kind === "language" ? values.total_timeout_seconds ?? null : null,
          extra_retries: values.extra_retries,
          temperature:
            configuration.values.temperature == null
              ? null
              : Number(configuration.values.temperature),
          max_tokens:
            configuration.values.max_tokens == null
              ? null
              : Number(configuration.values.max_tokens),
        };
        onSubmit(
          model
            ? { ...input, revision }
            : {
                ...input,
                provider_id: providerId,
                model_id: values.model_id.trim(),
                enabled: true,
              },
        );
      }}
    >
      <Form.Item label="供应商" required>
        <Select
          aria-label="供应商"
          disabled={busy || !!model}
          value={providerId}
          options={providers.map((p) => ({
            value: p.id,
            label: `${p.name} · ${p.protocol}`,
          }))}
          onChange={(id) => {
            setProviderId(id);
            const next = profiles.find(
              (p) =>
                p.protocol === providers.find((v) => v.id === id)?.protocol,
            );
            setKind(next?.kind ?? "language");
            choose(next);
          }}
        />
      </Form.Item>
      <Form.Item
        label="模型 ID"
        name="model_id"
        rules={[{ required: true, whitespace: true, message: "请输入模型 ID" }]}
      >
        <Input autoFocus disabled={busy || !!model} />
      </Form.Item>
      <Form.Item label="名称" name="display_name">
        <Input placeholder="留空使用模型 ID" />
      </Form.Item>
      <Form.Item label="模型种类" required>
        <Select
          aria-label="模型种类"
          value={kind}
          options={Object.entries(kindLabel).map(([value, label]) => ({
            value,
            label,
          }))}
          onChange={(v) => {
            setKind(v as ModelKind);
            choose(available.find((p) => p.kind === v));
          }}
        />
      </Form.Item>
      <Form.Item
        label="接口模式"
        name="api_mode"
        rules={[
          {
            validator: () =>
              selected
                ? Promise.resolve()
                : Promise.reject(new Error("请选择受支持的接口模式")),
          },
        ]}
      >
        <Select
          aria-label="接口模式"
          placeholder="此协议尚不支持该类模型"
          options={available
            .filter((p) => p.kind === kind)
            .map((p) => ({ value: p.api_mode, label: p.api_mode }))}
          onChange={(v) =>
            choose(available.find((p) => p.kind === kind && p.api_mode === v))
          }
        />
      </Form.Item>
      {!selected && (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          title="请选择供应商支持的模型种类和接口模式后保存。"
        />
      )}
      {selected && (
        <ModelConfigurationFields
          profile={selected}
          value={configuration}
          disabled={busy}
          onChange={(value) => {
            setConfiguration(value);
            onDirty();
          }}
        />
      )}
      <Form.Item
        label={kind === "language" ? "响应间隔超时（秒）" : "超时（秒）"}
        extra={kind === "language" ? "从发送请求开始等待首个有效增量，之后每收到正文、推理或工具参数增量重新计时；心跳不续期。" : undefined}
        name="timeout_seconds"
        rules={[
          {
            required: true,
            type: "number",
            message: "请输入大于 0 的秒数",
            validator: async (_, value) => {
              if (!withinNumericRule(value, fields.timeout_seconds ?? { label: "超时", type: "number", min: 0, exclusive_min: true })) {
                throw new Error("请输入大于 0 的秒数");
              }
            },
          },
        ]}
      >
        <InputNumber min={fields.timeout_seconds?.min} max={fields.timeout_seconds?.max} />
      </Form.Item>
      {kind === "language" && (
        <Form.Item
          label="单次请求总时限（秒）"
          name="total_timeout_seconds"
          extra="留空表示不限制；每次请求独立计时，模块总预算仍然生效。"
          rules={[{
            validator: async (_, value) => {
              if (value != null && (!withinNumericRule(value, fields.total_timeout_seconds ?? { label: "总时限", type: "number", min: 0, exclusive_min: true }))) {
                throw new Error("请输入大于 0 的秒数，或留空关闭");
              }
            },
          }]}
        >
          <InputNumber placeholder="不限制" />
        </Form.Item>
      )}
      <Form.Item
        label="失败后额外重试次数"
        name="extra_retries"
        extra="仅暂时故障重试。嵌入和重排当前每次只请求一次。"
        rules={[
          {
            required: true,
            type: "integer",
            min: fields.extra_retries?.min,
            max: fields.extra_retries?.max,
            message: "请输入允许范围内的整数",
          },
        ]}
      >
        <InputNumber min={fields.extra_retries?.min} max={fields.extra_retries?.max} />
      </Form.Item>
    </Form>
  );
}
