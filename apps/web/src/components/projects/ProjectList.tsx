"use client";
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  Modal,
  Pagination,
  Segmented,
  Space,
  type InputRef,
} from "antd";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageShell } from "@/components/PageShell";
import { Icon, type IconName } from "@/components/Icon";
import { createProject, listProjects } from "@/lib/api/client";
import { formatTime } from "@/lib/format";
import type { WireProject } from "@/types/projects";

type Filter = "all" | "pending" | "failed";
const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "全部项目" },
  { value: "pending", label: "待复核" },
  { value: "failed", label: "需要处理" },
];

function projectStatus(project: WireProject) {
  if ((project.failed_count ?? 0) > 0)
    return { label: "处理异常", tone: "failed" };
  if ((project.review_count ?? 0) > 0)
    return { label: "待复核", tone: "pending" };
  if ((project.file_count ?? 0) === 0) return { label: "待上传", tone: "" };
  // 无待办不等于已人工确认，避免把解析完成误报为已核实。
  return { label: "暂无待办", tone: "ready" };
}

export function ProjectList() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [dirty, setDirty] = useState(false);
  const [page, setPage] = useState(1);
  const [projects, setProjects] = useState<WireProject[] | null>(null);
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [view, setView] = useState<"grid" | "list">("grid");
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
      reviews: (projects ?? []).reduce(
        (sum, item) => sum + (item.review_count ?? 0),
        0,
      ),
      failures: (projects ?? []).reduce(
        (sum, item) => sum + (item.failed_count ?? 0),
        0,
      ),
    }),
    [projects],
  );
  const visible = (projects ?? []).filter((item) =>
    filter === "pending"
      ? (item.review_count ?? 0) > 0
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
      label: "待复核条目",
      value: totals.reviews,
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
      await createProject({
        name: draft.name.trim(),
        project_no: draft.project_no?.trim() || null,
        owner: draft.owner?.trim() || null,
      });
      form.resetFields();
      setDirty(false);
      void message.success("项目已创建");
      setCreating(false);
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
          <div className="view-switch" aria-label="项目显示方式">
            <button
              type="button"
              aria-label="卡片视图"
              aria-pressed={view === "grid"}
              onClick={() => setView("grid")}
            >
              <Icon name="grid" size={15} />
            </button>
            <button
              type="button"
              aria-label="列表视图"
              aria-pressed={view === "list"}
              onClick={() => setView("list")}
            >
              <Icon name="list" size={15} />
            </button>
          </div>
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
        {projects === null && loading ? (
          <div className="project-grid" role="status" aria-label="正在加载项目">
            {[0, 1, 2].map((i) => (
              <div className="project-card h-[230px]" key={i}>
                <div className="skeleton h-10 w-10" />
                <div className="skeleton mt-6 h-4 w-3/4" />
                <div className="skeleton mt-3 h-3 w-1/2" />
                <div className="skeleton mt-auto h-5 w-full" />
              </div>
            ))}
          </div>
        ) : projects !== null && visible.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">
              <Icon name={appliedKeyword ? "search" : "folder"} size={30} />
            </span>
            <h3>
              {appliedKeyword
                ? "没有找到匹配的项目"
                : filter !== "all"
                  ? "当前没有需要处理的项目"
                  : "把第一份标书交给 AI-Tender"}
            </h3>
            <p>
              {appliedKeyword
                ? "试试更短的名称或项目编号。"
                : filter !== "all"
                  ? "你可以切换到全部项目，查看文件与解析结果。"
                  : "新建项目，上传主文件、补遗或澄清材料，即可开始分析。"}
            </p>
            {appliedKeyword || filter !== "all" ? (
              <Button
                htmlType="button"
                onClick={() => {
                  setKeyword("");
                  setFilter("all");
                  void reload("");
                }}
              >
                查看全部项目
              </Button>
            ) : (
              <Button
                type="primary"
                htmlType="button"
                onClick={() => setCreating(true)}
              >
                <Icon name="plus" size={15} />
                新建项目
              </Button>
            )}
          </div>
        ) : (
          <div className={"project-grid " + (view === "list" ? "is-list" : "")}>
            {visible.slice((page - 1) * 12, page * 12).map((project) => {
              const status = projectStatus(project);
              return (
                <Link
                  href={"/projects/" + project.id}
                  key={project.id}
                  className="project-card"
                >
                  <div className="project-card-top">
                    <span className="folder-badge">
                      <Icon name="folder" size={22} />
                    </span>
                    <span className={"status-badge " + status.tone}>
                      {status.label}
                    </span>
                  </div>
                  <h3 title={project.name}>{project.name}</h3>
                  <p className="project-number">
                    {project.project_no || "尚未填写项目编号"}
                  </p>
                  <div className="project-card-data">
                    <span>
                      <Icon name="file" size={13} />
                      {project.file_count ?? 0} 个文件
                    </span>
                    <span>
                      <Icon name="clock" size={13} />
                      {project.review_count ?? 0} 项待复核
                    </span>
                  </div>
                  <div className="project-card-footer">
                    <span className="owner-avatar">
                      {project.owner?.slice(0, 1) || (
                        <Icon name="user" size={12} />
                      )}
                    </span>
                    <small>{project.owner || "未指定负责人"}</small>
                    <time
                      dateTime={project.last_activity_at ?? project.created_at}
                    >
                      {formatTime(
                        project.last_activity_at ?? project.created_at,
                      )}
                    </time>
                    <Icon name="arrow" size={15} />
                  </div>
                </Link>
              );
            })}
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
          showTotal={(total) => `共 ${total} 个项目`}
        />
      </section>

      <Modal
        open={creating}
        title="新建项目"
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
              创建项目
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
