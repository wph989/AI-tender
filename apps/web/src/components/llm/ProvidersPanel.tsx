"use client";
import { DataTable } from "@/components/DataTable";

import { useState } from "react";
import {
  Alert,
  App,
  Button,
  Checkbox,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
} from "antd";
import {
  createProvider,
  deleteProvider,
  importModels,
  listRemoteModels,
  testProvider,
  updateProvider,
} from "@/lib/api/llm";
import {
  countdownLabel,
  formatTime,
  message,
  validityLabel,
  kindLabel,
} from "@/lib/llm/format";
import type {
  AdapterProfile,
  LlmProvider,
  ProviderInput,
  ProviderPatchInput,
} from "@/types/llm";
import { useFeedback } from "@/hooks/useFeedback";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import {
  ModelConfigurationFields,
  defaultConfiguration,
  type ModelConfiguration,
} from "./ModelConfigurationFields";

interface Props {
  providers: LlmProvider[];
  profiles: AdapterProfile[];
  secretReady: boolean;
  onChanged: () => Promise<void>;
}

export function ProvidersPanel({
  providers,
  profiles,
  secretReady,
  onChanged,
}: Props) {
  const { modal, message: toast } = App.useApp();
  const [editing, setEditing] = useState<LlmProvider | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState<LlmProvider | null>(null);
  const [remote, setRemote] = useState<string[] | null>(null);
  const [importMode, setImportMode] = useState("");
  const [configuration, setConfiguration] = useState<ModelConfiguration | null>(
    null,
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const closeEditor = useUnsavedChanges(dirty, busy);
  useFeedback(error);
  const profile = profiles.find(
    (p) =>
      p.protocol === importing?.protocol &&
      (!importMode || p.api_mode === importMode),
  );

  const refresh = async () => {
    // 写入和刷新分开报告，避免写入成功后误导用户重复创建。
    await onChanged().catch(() =>
      setError("操作已完成，列表刷新失败，请点击刷新。"),
    );
  };
  const run = async (task: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (e) {
      setError(message(e, "操作失败"));
    } finally {
      setBusy(false);
    }
  };
  const edit = (provider: LlmProvider | "new") => {
    setDirty(false);
    setError(null);
    setEditing(provider);
  };
  const save = (input: ProviderInput | ProviderPatchInput) =>
    void run(async () => {
      if (editing === "new") await createProvider(input as ProviderInput);
      else if (editing) await updateProvider(editing.id, input);
      setDirty(false);
      setEditing(null);
      void toast.success("供应商已保存");
      await refresh();
    });
  const openRemote = (provider: LlmProvider) =>
    void run(async () => {
      setImporting(provider);
      setRemote(null);
      setSelected([]);
      setSearch("");
      setImportMode("");
      setConfiguration(null);
      setRemote(await listRemoteModels(provider.id));
    });
  const importSelected = () =>
    void run(async () => {
      if (!importing || !profile) return;
      const config = configuration ?? defaultConfiguration(profile);
      const count = await importModels(importing.id, selected, profile, {
        capabilities: config.capabilities,
        supported_parameters: config.supported,
        parameters: Object.fromEntries(
          Object.entries(config.values).filter(
            ([key]) => !["temperature", "max_tokens"].includes(key),
          ),
        ),
        temperature:
          config.values.temperature == null
            ? null
            : Number(config.values.temperature),
        max_tokens:
          config.values.max_tokens == null
            ? null
            : Number(config.values.max_tokens),
      });
      void toast.success(
        `已导入 ${count} 个模型，跳过 ${selected.length - count} 个已有模型。新模型默认启用。`,
      );
      setImporting(null);
      await refresh();
    });

  return (
    <section className="ui-panel settings-panel p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">供应商</h2>
          <p className="mt-1 text-sm text-slate-500">
            配置服务连接；模型的具体能力在「管理模型」中测试。
          </p>
        </div>
        <Button type="primary" disabled={busy} onClick={() => edit("new")}>
          新增供应商
        </Button>
      </div>
      {!secretReady && (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          title="密钥存储尚未配置，可保存连接信息或使用匿名服务。"
        />
      )}
      {error && !editing && !importing && (
        <Alert className="mb-4" type="error" showIcon title={error} />
      )}
      <DataTable<LlmProvider>
        rowKey="id"
        dataSource={providers}
        size="middle"
        scroll={{ x: 900 }}
        pagination={{
          defaultPageSize: 10,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个供应商`,
        }}
        locale={{
          emptyText: <Empty description="暂无供应商，点击新增供应商配置连接" />,
        }}
        columns={[
          {
            title: "名称",
            key: "name",
            width: 180,
            render: (_, p) => (
              <>
                <strong>{p.name}</strong>
                <div className="text-xs text-slate-500">{p.protocol}</div>
              </>
            ),
          },
          {
            title: "服务地址",
            dataIndex: "base_url",
            width: 230,
            render: (value: string) => (
              <span className="break-all">{value}</span>
            ),
          },
          {
            title: "密钥",
            key: "key",
            width: 110,
            render: (_, p) =>
              p.auth_mode === "none"
                ? "匿名"
                : p.has_api_key
                  ? (p.api_key_hint ?? "已配置")
                  : "未配置",
          },
          {
            title: "状态",
            key: "state",
            width: 150,
            render: (_, p) => (
              <>
                <Tag color={p.enabled ? "success" : "default"}>
                  {p.enabled ? "启用" : "停用"}
                </Tag>
                {p.rate_limit_remaining_seconds > 0 && (
                  // 429 后本页只读展示冷却，不提供手动解除：计时来自后端共享截止时间。
                  <div className="mt-1">
                    <Tag color="warning">
                      限流冷却 {countdownLabel(p.rate_limit_remaining_seconds)}
                    </Tag>
                  </div>
                )}
              </>
            ),
          },
          {
            title: "最近测试",
            key: "test",
            width: 200,
            render: (_, p) => (
              <>
                {validityLabel(p.test_validity)}
                <div className="text-xs text-slate-500">
                  {formatTime(p.last_test_at)}
                </div>
                {p.last_test_error && (
                  <p className="break-all text-xs text-rose-700">
                    {p.last_test_error}
                  </p>
                )}
              </>
            ),
          },
          {
            title: "操作",
            key: "actions",
            width: 260,
            render: (_, p) => (
              <Space wrap>
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      const result = await testProvider(p.id);
                      if (result.status === "ok")
                        void toast.success("连接测试成功");
                      else setError(result.error ?? "连接测试未通过");
                      await refresh();
                    })
                  }
                >
                  测试
                </Button>
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() => openRemote(p)}
                >
                  拉取模型
                </Button>
                <Button size="small" disabled={busy} onClick={() => edit(p)}>
                  编辑
                </Button>
                <Button
                  size="small"
                  danger
                  disabled={busy}
                  onClick={() =>
                    modal.confirm({
                      title: `删除供应商「${p.name}」？`,
                      content: "仍被功能绑定的模型会阻止删除。",
                      okText: "删除",
                      okButtonProps: { danger: true },
                      onOk: async () => {
                        try {
                          await deleteProvider(p.id);
                          void toast.success("供应商已删除");
                          await refresh();
                        } catch (e) {
                          setError(message(e, "删除失败"));
                          throw e;
                        }
                      },
                    })
                  }
                >
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
      />
      {/* 弹层挂载到 body，分页、表格滚动及页头位置都不会遮住编辑入口。 */}
      <Modal
        title={
          editing === "new"
            ? "新增供应商"
            : `编辑供应商 · ${editing?.name ?? ""}`
        }
        open={editing !== null}
        width={600}
        centered
        destroyOnHidden
        mask={{ closable: false }}
        keyboard={!busy}
        closable={!busy}
        onCancel={() => closeEditor(() => { setEditing(null); setDirty(false); setError(null); })}
        className="editor-modal"
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
              form="provider-form"
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
          <ProviderForm
            key={editing === "new" ? "new" : editing.id}
            provider={editing === "new" ? null : editing}
            profiles={profiles}
            secretReady={secretReady}
            busy={busy}
            onSubmit={save}
            onDirty={() => setDirty(true)}
          />
        )}
      </Modal>
      <Modal
        title={`导入模型 · ${importing?.name ?? ""}`}
        open={importing !== null}
        width={760}
        centered
        className="editor-modal"
        destroyOnHidden
        mask={{ closable: false }}
        keyboard={!busy}
        closable={!busy}
        onCancel={() => setImporting(null)}
        footer={
          <Space>
            <Button disabled={busy} onClick={() => setImporting(null)}>
              取消
            </Button>
            <Button
              type="primary"
              htmlType="submit"
              form="import-models"
              loading={busy}
              disabled={!selected.length || !profile}
            >
              导入 {selected.length} 个模型
            </Button>
          </Space>
        }
      >
        {error && (
          <Alert
            className="mb-4"
            type="error"
            showIcon
            title={error}
            action={
              <Button
                size="small"
                disabled={busy}
                onClick={() => importing && openRemote(importing)}
              >
                重新拉取
              </Button>
            }
          />
        )}
        {remote === null ? (
          busy && (
            <Spin tip="正在拉取模型">
              <div className="h-24" />
            </Spin>
          )
        ) : (
          /* 这个表单只为下方能力与参数字段提供 Form 上下文，唯一的提交入口是页脚的
             「导入 N 个模型」按钮。不在表单层拦 Enter 的话，在搜索框或参数输入框里回车
             会触发浏览器的隐式提交，直接把已勾选的模型导入（一次创建模型的写请求）。 */
          <Form
            id="import-models"
            layout="vertical"
            disabled={busy}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.preventDefault();
            }}
            onFinish={importSelected}
          >
            <p className="mb-4 text-sm text-slate-500">
              选择模型并核对能力。已有模型会跳过，新模型默认启用。
            </p>
            <Form.Item label="导入模型能力">
              <Select
                value={profile?.api_mode}
                onChange={(mode) => {
                  setImportMode(mode);
                  setConfiguration(null);
                }}
                options={profiles
                  .filter((p) => p.protocol === importing?.protocol)
                  .map((p) => ({
                    value: p.api_mode,
                    label: `${kindLabel[p.kind]} · ${p.api_mode}`,
                  }))}
              />
            </Form.Item>
            {profile && (
              <ModelConfigurationFields
                profile={profile}
                value={configuration ?? defaultConfiguration(profile)}
                onChange={setConfiguration}
                disabled={busy}
              />
            )}
            <Input.Search
              className="my-4"
              aria-label="搜索远端模型"
              placeholder="搜索远端模型"
              allowClear
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <DataTable<{ id: string }>
              size="small"
              rowKey="id"
              dataSource={remote
                .filter((id) => id.toLowerCase().includes(search.toLowerCase()))
                .map((id) => ({ id }))}
              columns={[
                {
                  title: "模型 ID",
                  dataIndex: "id",
                  render: (id: string) => (
                    <span className="break-all">{id}</span>
                  ),
                },
              ]}
              rowSelection={{
                selectedRowKeys: selected,
                preserveSelectedRowKeys: true,
                onChange: (keys) => setSelected(keys as string[]),
                getCheckboxProps: () => ({ disabled: busy }),
              }}
              pagination={{ defaultPageSize: 8, showSizeChanger: false }}
              locale={{ emptyText: "没有匹配的远端模型" }}
            />
          </Form>
        )}
      </Modal>
    </section>
  );
}

interface ProviderValues {
  name: string;
  protocol: string;
  base_url: string;
  auth_mode: "api_key" | "none";
  api_key?: string;
  clear_api_key?: boolean;
  enabled: boolean;
}

function ProviderForm({
  provider,
  profiles,
  secretReady,
  busy,
  onSubmit,
  onDirty,
}: {
  provider: LlmProvider | null;
  profiles: AdapterProfile[];
  secretReady: boolean;
  busy: boolean;
  onSubmit: (input: ProviderInput | ProviderPatchInput) => void;
  onDirty: () => void;
}) {
  const [form] = Form.useForm<ProviderValues>();
  const auth = Form.useWatch("auth_mode", form);
  const clearKey = Form.useWatch("clear_api_key", form);
  return (
    <Form
      form={form}
      id="provider-form"
      layout="vertical"
      disabled={busy}
      onValuesChange={onDirty}
      scrollToFirstError={{ focus: true }}
      initialValues={{
        name: provider?.name ?? "",
        protocol:
          provider?.protocol ?? profiles[0]?.protocol ?? "openai_compatible",
        base_url: provider?.base_url ?? "",
        auth_mode: provider?.auth_mode ?? "api_key",
        enabled: provider?.enabled ?? true,
      }}
      onFinish={(values) => {
        const common = {
          name: values.name.trim(),
          base_url: values.base_url.trim(),
          auth_mode: values.auth_mode,
          enabled: values.enabled,
        };
        // 密钥只写不读：空白保持原值，清除由独立复选项明确表达。
        const key = values.clear_api_key
          ? { clear_api_key: true }
          : values.api_key && values.auth_mode !== "none"
            ? { api_key: values.api_key }
            : {};
        onSubmit(
          provider
            ? { ...common, ...key, revision: provider.revision }
            : { ...common, ...key, protocol: values.protocol },
        );
      }}
    >
      <Form.Item
        name="name"
        label="名称"
        rules={[
          { required: true, whitespace: true, message: "请输入供应商名称" },
          { max: 200, message: "名称最多 200 字" },
        ]}
      >
        <Input autoFocus placeholder="例如：内网网关" maxLength={200} />
      </Form.Item>
      <Form.Item
        name="protocol"
        label="协议"
        rules={[{ required: true, message: "请选择协议" }]}
      >
        <Select
          disabled={busy || provider !== null}
          options={Array.from(new Set(profiles.map((p) => p.protocol))).map(
            (value) => ({ value, label: value }),
          )}
        />
      </Form.Item>
      <Form.Item name="auth_mode" label="认证">
        <Select
          options={[
            { value: "api_key", label: "API Key" },
            { value: "none", label: "匿名服务（无需密钥）" },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="base_url"
        label="服务地址（Base URL）"
        rules={[
          { required: true, whitespace: true, message: "请输入服务地址" },
          {
            validator: (_, value: string) => {
              try {
                const url = new URL(value.trim());
                if (["http:", "https:"].includes(url.protocol))
                  return Promise.resolve();
              } catch {}
              return Promise.reject(
                new Error("请输入完整的 http:// 或 https:// 地址"),
              );
            },
          },
        ]}
      >
        <Input placeholder="https://gateway.example/v1" />
      </Form.Item>
      <Form.Item
        name="api_key"
        label="API Key"
        extra={
          provider
            ? "留空保持现有密钥；已保存的密钥不会回显。"
            : "也可稍后填写，调用前需完成配置。"
        }
      >
        <Input.Password
          autoComplete="new-password"
          disabled={busy || !secretReady || clearKey || auth === "none"}
        />
      </Form.Item>
      <Form.Item name="enabled" label="启用供应商" valuePropName="checked">
        <Switch />
      </Form.Item>
      {provider && (
        <Form.Item name="clear_api_key" valuePropName="checked">
          <Checkbox>清除已保存的密钥</Checkbox>
        </Form.Item>
      )}
    </Form>
  );
}
