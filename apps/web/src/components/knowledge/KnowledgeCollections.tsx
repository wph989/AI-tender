"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Segmented,
  Empty,
  Form,
  Input,
  Modal,
  Tag,
  Select,
  Skeleton,
  Space,
} from "antd";
import { DataPagination } from "@/components/DataPagination";
import { DataTable } from "@/components/DataTable";
import { PageShell } from "@/components/PageShell";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { knowledgeRequest } from "@/lib/api/knowledge";
import { PURPOSE_LABELS, type KnowledgeCollection } from "@/types/knowledge";

export function KnowledgeCollections() {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const [items, setItems] = useState<KnowledgeCollection[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
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
  // 删除末页最后一条时，卡片切片与分页组件使用同一个有效页码。
  const currentPage = Math.min(
    page,
    Math.max(1, Math.ceil(visible.length / 12)),
  );
  const collectionActions = (item: KnowledgeCollection) => (
    <Space size={4} wrap>
      <Button type="link" href={`/knowledge/${item.id}`}>
        打开
      </Button>
      <Button type="text" href={`/projects/${item.upload_project_id}/files`}>
        管理文件
      </Button>
      {item.is_project ? (
        <Button type="text" href={`/projects/${item.upload_project_id}`}>
          查看项目
        </Button>
      ) : (
        <Button
          type="text"
          danger
          disabled={busy}
          onClick={() =>
            modal.confirm({
              title: `删除知识库「${item.name}」？`,
              content:
                "关联项目将无法继续检索其中的资料，相关引用会变为不可用。",
              okText: "删除知识库",
              cancelText: "取消",
              okButtonProps: { danger: true },
              onOk: async () => {
                setBusy(true);
                try {
                  await knowledgeRequest(
                    `/knowledge/collections/${item.id}`,
                    "DELETE",
                  );
                  setItems(
                    (rows) => rows?.filter((row) => row.id !== item.id) ?? null,
                  );
                  void message.success("知识库已删除");
                  await reload();
                } catch (caught) {
                  void message.error(
                    caught instanceof Error
                      ? caught.message
                      : "删除知识库失败",
                  );
                  throw caught;
                } finally {
                  setBusy(false);
                }
              },
            })
          }
        >
          删除
        </Button>
      )}
    </Space>
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
      <div className="list-toolbar">
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
      <Segmented aria-label="知识库显示方式" value={view}
        options={[{ value: "grid", label: "卡片视图" }, { value: "list", label: "列表视图" }]}
        onChange={setView} />
      </div>
      {loading && items === null ? (
        <Skeleton active />
      ) : items !== null && !visible.length ? (
        <Empty
          description={
            search ? "没有匹配的知识库" : "暂无知识库，点击新建知识库后上传资料"
          }
        />
      ) : view === "grid" ? <>
        <div className="knowledge-grid">
          {visible.slice((currentPage - 1) * 12, currentPage * 12).map((item) => <Card key={item.id}
            title={<Link href={`/knowledge/${item.id}`}>{item.name}</Link>}
            className="project-summary-card">
            <div className="project-summary-meta"><Tag>{item.is_project ? "项目资料库" : PURPOSE_LABELS[item.purpose]}</Tag>
              <span>{item.file_count} 份资料</span></div>
            <div className="project-summary-actions">{collectionActions(item)}</div>
          </Card>)}
        </div>
        <DataPagination current={currentPage}
          pageSize={12} total={visible.length} onChange={setPage} />
      </> : (
        <DataTable<KnowledgeCollection> rowKey="id" dataSource={visible} loading={loading}
          pagination={{ current: currentPage,
            pageSize: 12, onChange: setPage, hideOnSinglePage: true, showSizeChanger: false,
            showTotal: (total) => `共 ${total} 个知识库` }}
          columns={[
            { title: "知识库名称", dataIndex: "name", width: 300, render: (_, item) =>
              <Link className="table-title" href={`/knowledge/${item.id}`}>{item.name}</Link> },
            { title: "用途", key: "purpose", width: 170, render: (_, item) =>
              <Tag>{item.is_project ? "项目资料库" : PURPOSE_LABELS[item.purpose]}</Tag> },
            { title: "资料数量", dataIndex: "file_count", width: 110, render: (value) => `${value} 份` },
            { title: "操作", key: "actions", width: 260, fixed: "right", render: (_, item) =>
collectionActions(item) },
          ]} />
      )}
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
