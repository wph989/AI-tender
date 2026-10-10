"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  App,
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Pagination,
  Select,
  Skeleton,
  Space,
} from "antd";
import { PageShell } from "@/components/PageShell";
import { Icon } from "@/components/Icon";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { knowledgeRequest } from "@/lib/api/knowledge";
import { PURPOSE_LABELS, type KnowledgeCollection } from "@/types/knowledge";

export function KnowledgeCollections() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [items, setItems] = useState<KnowledgeCollection[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const close = useUnsavedChanges(dirty, busy);
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(
        (
          await knowledgeRequest<{ items: KnowledgeCollection[] }>(
            "/knowledge/collections",
          )
        ).items,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载知识库失败");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  const cancel = () =>
    close(() => {
      setCreating(false);
      setDirty(false);
      form.resetFields();
    });
  const visible = (items ?? []).filter((item) =>
    item.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <PageShell
      eyebrow="知识库"
      title="知识库"
      description="整理企业资料、历史标书与项目材料，关联项目后即可检索和核对原文。"
      actions={
        <Space>
          <Button loading={loading} onClick={() => void reload()}>
            刷新
          </Button>
          <Button
            type="primary"
            onClick={() => {
              setCreateError(null);
              setCreating(true);
            }}
          >
            新建知识库
          </Button>
        </Space>
      }
    >
      {error && (
        <Alert
          type="error"
          showIcon
          title={error}
          className="mb-4"
          action={
            <Button size="small" onClick={() => void reload()}>
              重试
            </Button>
          }
        />
      )}
      <Input.Search
        className="mb-5"
        style={{ width: 320, maxWidth: "100%" }}
        aria-label="搜索知识库"
        placeholder="搜索知识库名称"
        allowClear
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />
      {loading && items === null ? (
        <Skeleton active />
      ) : items !== null && !visible.length ? (
        <Empty
          description={
            search ? "没有匹配的知识库" : "暂无知识库，点击新建知识库后上传资料"
          }
        />
      ) : (
        <div className="knowledge-grid">
          {visible.slice((page - 1) * 12, page * 12).map((item) => (
            <Link
              key={item.id}
              href={"/knowledge/" + item.id}
              className="knowledge-card"
            >
              <div className="flex items-center gap-3">
                <span className="knowledge-card-icon">
                  <Icon name={item.is_project ? "folder" : "book"} size={23} />
                </span>
                <span className="text-xs text-slate-500">
                  {item.is_project
                    ? "项目资料库"
                    : PURPOSE_LABELS[item.purpose]}
                </span>
              </div>
              <h2>{item.name}</h2>
              <div className="flex items-center justify-between text-sm text-slate-500">
                <span>{item.file_count} 份资料</span>
                <span className="text-violet-700">打开资料库 ↗</span>
              </div>
            </Link>
          ))}
        </div>
      )}
      <Pagination
        className="mt-5"
        current={page}
        pageSize={12}
        total={visible.length}
        onChange={setPage}
        hideOnSinglePage
        showSizeChanger={false}
      />
      <Modal
        open={creating}
        title="新建知识库"
        centered
        destroyOnHidden
        mask={{ closable: false }}
        keyboard={!busy}
        closable={!busy}
        onCancel={cancel}
        className="editor-modal"
        footer={
          <Space>
            <Button disabled={busy} onClick={cancel}>
              取消
            </Button>
            <Button
              type="primary"
              htmlType="submit"
              form="create-collection"
              loading={busy}
            >
              创建知识库
            </Button>
          </Space>
        }
      >
        {createError && (
          <Alert className="mb-4" type="error" showIcon title={createError} />
        )}
        <Form
          form={form}
          id="create-collection"
          layout="vertical"
          disabled={busy}
          initialValues={{ purpose: "company" }}
          onValuesChange={() => setDirty(true)}
          scrollToFirstError={{ focus: true }}
          onFinish={async (values: { name: string; purpose: string }) => {
            if (busy) return;
            setBusy(true);
            setCreateError(null);
            try {
              await knowledgeRequest("/knowledge/collections", "POST", {
                ...values,
                name: values.name.trim(),
              });
              form.resetFields();
              setDirty(false);
              setCreating(false);
              setSearch("");
              setPage(1);
              void message.success("知识库已创建");
              await reload();
            } catch (e) {
              setCreateError(e instanceof Error ? e.message : "创建失败");
            } finally {
              setBusy(false);
            }
          }}
        >
          <Form.Item
            label="知识库名称"
            name="name"
            rules={[
              { required: true, whitespace: true, message: "请输入知识库名称" },
              { max: 200, message: "最多 200 字" },
            ]}
          >
            <Input
              autoFocus
              maxLength={200}
              placeholder="例如：公司资质与证明材料"
            />
          </Form.Item>
          <Form.Item
            label="资料用途"
            name="purpose"
            rules={[{ required: true, message: "请选择资料用途" }]}
          >
            <Select
              options={Object.entries(PURPOSE_LABELS).map(([value, label]) => ({
                value,
                label,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
