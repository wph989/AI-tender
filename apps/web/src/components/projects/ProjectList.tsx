"use client";
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Empty,
  Tag,
  Segmented,
  Space,
  type InputRef,
} from "antd";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DataPagination } from "@/components/DataPagination";
import { DataTable } from "@/components/DataTable";
import { PageShell } from "@/components/PageShell";
import { Icon, type IconName } from "@/components/Icon";
import { createProject, deleteProject, listProjects, updateProject } from "@/lib/api/client";
import { formatTime } from "@/lib/format";
import type { WireProject } from "@/types/projects";

type Filter = "all" | "empty" | "failed";
const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "全部项目" },
  { value: "empty", label: "待上传" },
  { value: "failed", label: "需要处理" },
];

function projectStatus(project: WireProject) {
  if ((project.failed_count ?? 0) > 0)
    return { label: "处理异常", tone: "failed" };
  if ((project.file_count ?? 0) === 0) return { label: "待上传", tone: "" };
  return { label: "已归档", tone: "ready" };
}

export function ProjectList() {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const [dirty, setDirty] = useState(false);
  const [page, setPage] = useState(1);
  const [projects, setProjects] = useState<WireProject[] | null>(null);
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [editing, setEditing] = useState<WireProject | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const closeEditor = useUnsavedChanges(dirty, busy);
  const searchRef = useRef<InputRef>(null);
  const requestId = useRef(0);

  const reload = useCallback(async (search: string) => {
    // 快速连续搜索时只接纳最后一次响应，防止旧结果覆盖新关键词。
    const id = ++requestId.current;
    setLoading(true);
    try {
      const items = await listProjects(search);
      if (id !== requestId.current) return;
      setProjects(items);
      setPage(1);
      setAppliedKeyword(search);
      setError(null);
    } catch (caught) {
      if (id === requestId.current)
        setError(
          caught instanceof Error ? caught.message : "加载项目失败，请重试。",
        );
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload("");
    return () => {
      requestId.current += 1;
    };
  }, [reload]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key !== "/" ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        creating
      )
        return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
      )
        return;
      event.preventDefault();
      searchRef.current?.focus();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [creating]);

  const totals = useMemo(
    () => ({
      files: (projects ?? []).reduce(
        (sum, item) => sum + (item.file_count ?? 0),
        0,
      ),
      empty: (projects ?? []).filter((item) => (item.file_count ?? 0) === 0).length,
      failures: (projects ?? []).reduce(
        (sum, item) => sum + (item.failed_count ?? 0),
        0,
      ),
    }),
    [projects],
  );
  const visible = (projects ?? []).filter((item) =>
    filter === "empty"
      ? (item.file_count ?? 0) === 0
      : filter === "failed"
        ? (item.failed_count ?? 0) > 0
        : true,
  );
  const metrics: {
    icon: IconName;
    label: string;
    value: number;
    tone: string;
  }[] = [
    {
      icon: "folder",
      label: "项目总数",
      value: projects?.length ?? 0,
      tone: "",
    },
    { icon: "file", label: "已归档文件", value: totals.files, tone: "green" },
    {
      icon: "clock",
      label: "待上传项目",
      value: totals.empty,
      tone: "orange",
    },
    { icon: "alert", label: "异常文件", value: totals.failures, tone: "red" },
  ];

  const submit = async (draft: {
    name: string;
    project_no?: string;
    owner?: string;
  }) => {
    if (busy) return;
    setBusy(true);
    setCreateError(null);
    try {
      const input = {
        name: draft.name.trim(),
        project_no: draft.project_no?.trim() || null,
        owner: draft.owner?.trim() || null,
      };
      if (editing) await updateProject(editing.id, input);
      else await createProject(input);
      form.resetFields();
      setDirty(false);
      void message.success(editing ? "项目信息已更新" : "项目已创建");
      setCreating(false);
      setEditing(null);
      setKeyword("");
      setFilter("all");
      await reload("");
    } catch (caught) {
      setCreateError(
        caught instanceof Error ? caught.message : "创建失败，请重试。",
      );
    } finally {
      setBusy(false);
    }
  };

  // 删除末页最后一条时，卡片切片与分页组件使用同一个有效页码。
  const currentPage = Math.min(
    page,
    Math.max(1, Math.ceil(visible.length / 12)),
  );
  const projectActions = (project: WireProject) => (
    <Space size={4} wrap>
      <Button type="link" href={`/projects/${project.id}`}>
        打开
      </Button>
      <Button
        type="text"
        disabled={busy}
        onClick={() => {
          setEditing(project);
          form.setFieldsValue(project);
          setDirty(false);
          setCreateError(null);
          setCreating(true);
        }}
      >
        编辑
      </Button>
      <Button
        type="text"
        danger
        disabled={busy}
        onClick={() =>
          modal.confirm({
            title: `删除项目「${project.name}」？`,
            content:
              "项目及其资料将无法继续访问，相关报告引用会受影响。此操作无法在页面中撤销。",
            okText: "删除项目",
            cancelText: "取消",
            okButtonProps: { danger: true },
            onOk: async () => {
              setBusy(true);
              try {
                await deleteProject(project.id);
                // 先移除已删除行，刷新失败也不能让它继续显示为可操作。
                setProjects(
                  (rows) => rows?.filter((row) => row.id !== project.id) ?? null,
                );
                void message.success("项目已删除");
                await reload(appliedKeyword);
              } catch (caught) {
                void message.error(
                  caught instanceof Error ? caught.message : "删除项目失败",
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
    </Space>
  );

  return (
    <PageShell
      eyebrow="项目空间"
      title="项目空间"
      description="从一份招标文件开始，让分析、核对与决策井然有序。"
      actions={
        <Button
          type="primary"
          htmlType="button"
          onClick={() => {
            setCreateError(null);
            setEditing(null);
            form.resetFields();
            setCreating(true);
          }}
        >
          <Icon name="plus" size={16} />
          新建项目
        </Button>
      }
    >
      <section
        aria-label={appliedKeyword ? "搜索结果统计" : "项目概览"}
        className="overview-strip"
      >
        {metrics.map((item) => (
          <div className="overview-item" key={item.label}>
            <span className={"overview-icon " + item.tone}>
              <Icon name={item.icon} size={20} />
            </span>
            <div>
              <p className="overview-value">
                {projects === null ? "—" : item.value}
              </p>
              <p className="overview-label">
                {appliedKeyword ? "搜索内 · " : ""}
                {item.label}
              </p>
            </div>
          </div>
        ))}
      </section>

      <section aria-labelledby="projects-title" aria-busy={loading}>
        <div className="section-bar">
          <h2 id="projects-title">
            我的项目{" "}
            <span className="count-pill">
              {projects === null ? "—" : visible.length}
            </span>
          </h2>
          <span className="text-[11px] text-slate-400">
            进入项目，继续核对招标要点
          </span>
        </div>
        <div className="project-tools">
          <Segmented
            aria-label="项目状态筛选"
            value={filter}
            options={FILTERS}
            onChange={(value) => {
              setFilter(value);
              setPage(1);
            }}
          />
          <form
            className="ml-auto flex min-w-0 items-center gap-2 max-md:w-full"
            onSubmit={(event) => {
              event.preventDefault();
              void reload(keyword.trim());
            }}
          >
            <div className="search-field">
              <Icon name="search" size={16} />
              <Input
                ref={searchRef}
                aria-label="按名称或编号搜索项目"
                placeholder="搜索项目名称或编号"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
              />
              <kbd>/</kbd>
            </div>
            <Button type="text" htmlType="submit" disabled={loading}>
              搜索
            </Button>
          </form>
          <Button
            type="text"
            htmlType="button"
            aria-label="刷新项目"
            title="刷新项目"
            disabled={loading}
            onClick={() => void reload(appliedKeyword)}
          >
            <Icon name="refresh" size={16} />
          </Button>
          <Segmented
            aria-label="项目显示方式"
            value={view}
            options={[
              {
                value: "grid",
                label: "卡片视图",
                icon: <Icon name="grid" size={15} />,
              },
              {
                value: "list",
                label: "列表视图",
                icon: <Icon name="list" size={15} />,
              },
            ]}
            onChange={setView}
          />
        </div>
        {error && (
          <div className="notice mb-5" role="alert">
            <Icon name="alert" />
            <span className="flex-1">{error}</span>
            <Button
              htmlType="submit"
              onClick={() => void reload(appliedKeyword)}
            >
              重试
            </Button>
          </div>
        )}
        {view === "grid" ? (
          <>
            <div className="project-grid" aria-label="项目卡片">
              {loading && projects === null
                ? [0, 1, 2].map((id) => <Card key={id} loading />)
                : visible
                    .slice((currentPage - 1) * 12, currentPage * 12)
                    .map((project) => (
                      <Card
                        key={project.id}
                        className="project-summary-card"
                        title={
                          <Link href={`/projects/${project.id}`}>
                            {project.name}
                          </Link>
                        }
                        extra={
                          <Tag
                            color={
                              projectStatus(project).tone === "failed"
                                ? "error"
                                : "default"
                            }
                          >
                            {projectStatus(project).label}
                          </Tag>
                        }
                      >
                        <p className="table-meta">
                          {project.project_no || "未填写项目编号"}
                        </p>
                        <div className="project-summary-meta">
                          <span>负责人 · {project.owner || "未指定"}</span>
                          <Link href={`/projects/${project.id}/files`}>
                            {project.file_count ?? 0} 份文件
                          </Link>
                        </div>
                        <p className="table-meta">
                          最近活动 ·{" "}
                          {formatTime(
                            project.last_activity_at ?? project.created_at,
                          )}
                        </p>
                        <div className="project-summary-actions">
                          {projectActions(project)}
                        </div>
                      </Card>
                    ))}
            </div>
            {!loading && !visible.length && (
              <Empty
                description={
                  appliedKeyword || filter !== "all"
                    ? "没有匹配的项目"
                    : "暂无项目，点击新建项目"
                }
              />
            )}
            <DataPagination
              current={currentPage}
              pageSize={12}
              total={visible.length}
              onChange={setPage}
            />
          </>
        ) : (
          <DataTable<WireProject>
            rowKey="id"
            dataSource={visible}
            loading={loading}
            pagination={{
              current: currentPage,
              pageSize: 12,
              onChange: setPage,
            }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    appliedKeyword
                      ? "没有找到匹配的项目"
                      : filter !== "all"
                        ? "当前筛选下没有项目"
                        : "暂无项目，点击右上方新建项目"
                  }
                />
              ),
            }}
            columns={[
              {
                title: "项目名称 / 编号",
                key: "name",
                width: 300,
                render: (_, project) => (
                  <div>
                    <Link
                      className="table-title"
                      href={`/projects/${project.id}`}
                    >
                      {project.name}
                    </Link>
                    <div className="table-meta">
                      {project.project_no || "未填写编号"}
                    </div>
                  </div>
                ),
              },
              {
                title: "负责人",
                dataIndex: "owner",
                width: 140,
                render: (value) => value || "未指定",
              },
              {
                title: "文件",
                key: "files",
                width: 100,
                render: (_, project) => (
                  <Link href={`/projects/${project.id}/files`}>
                    {project.file_count ?? 0} 份
                  </Link>
                ),
              },
              {
                title: "状态",
                key: "status",
                width: 130,
                render: (_, project) => {
                  const status = projectStatus(project);
                  const color =
                    status.tone === "failed"
                      ? "error"
                      : status.tone === "ready"
                        ? "success"
                        : "default";
                  return <Tag color={color}>{status.label}</Tag>;
                },
              },
              {
                title: "最近活动",
                key: "activity",
                width: 180,
                render: (_, project) =>
                  formatTime(project.last_activity_at ?? project.created_at),
              },
              {
                title: "操作",
                key: "actions",
                width: 180,
                fixed: "right",
                render: (_, project) => projectActions(project),
              },
            ]}
          />
        )}
      </section>

      <Modal
        open={creating}
        title={editing ? "编辑项目" : "新建项目"}
        centered
        width={520}
        destroyOnHidden
        mask={{ closable: false }}
        keyboard={!busy}
        closable={!busy}
        className="editor-modal"
        onCancel={() =>
          closeEditor(() => {
            setCreating(false);
            form.resetFields();
            setDirty(false);
          })
        }
        footer={
          <Space>
            <Button
              disabled={busy}
              onClick={() =>
                closeEditor(() => {
                  setCreating(false);
                  form.resetFields();
                  setDirty(false);
                })
              }
            >
              取消
            </Button>
            <Button
              type="primary"
              htmlType="submit"
              form="create-project"
              loading={busy}
            >
              {editing ? "保存修改" : "创建项目"}
            </Button>
          </Space>
        }
      >
        <p className="mb-4 text-sm text-slate-500">
          集中管理本次投标的文件与分析结果。
        </p>
        {createError && (
          <Alert className="mb-4" type="error" showIcon title={createError} />
        )}
        <Form
          form={form}
          id="create-project"
          layout="vertical"
          disabled={busy}
          onFinish={submit}
          onValuesChange={() => setDirty(true)}
          scrollToFirstError={{ focus: true }}
        >
          <Form.Item
            name="name"
            label="项目名称"
            rules={[
              { required: true, whitespace: true, message: "请输入项目名称" },
              { max: 200, message: "最多 200 字" },
            ]}
          >
            <Input
              autoFocus
              maxLength={200}
              placeholder="例如：智慧园区信息化建设项目"
            />
          </Form.Item>
          <Form.Item name="project_no" label="项目编号（选填）">
            <Input maxLength={100} placeholder="输入招标编号" />
          </Form.Item>
          <Form.Item name="owner" label="负责人（选填）">
            <Input maxLength={100} placeholder="输入负责人姓名" />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
