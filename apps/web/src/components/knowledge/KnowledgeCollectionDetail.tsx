"use client";
import { Alert, App, Button, Form, Input, Modal, Space } from "antd";
import { useFeedback } from "@/hooks/useFeedback";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PageShell } from "@/components/PageShell";
import { UploadPanel } from "@/components/projects/UploadPanel";
import { BUTTON_CLASS } from "@/components/ui";
import { deleteProjectFile, uploadProjectFiles } from "@/lib/api/client";
import { knowledgeRequest, resolveCitation } from "@/lib/api/knowledge";
import {
  PURPOSE_LABELS,
  STATE_LABELS,
  type Citation,
  type KnowledgeCollection,
} from "@/types/knowledge";
import { CitationViewer } from "./CitationViewer";
import { QuestionPanel } from "./QuestionPanel";

interface SearchHit extends Citation {
  content: string;
  chapter: string;
}

export function KnowledgeCollectionDetail({
  collectionId,
}: {
  collectionId: number;
}) {
  const { modal, message: toast } = App.useApp();
  const [renameForm] = Form.useForm();
  const [renaming, setRenaming] = useState(false);
  const [renameDirty, setRenameDirty] = useState(false);
  const router = useRouter();
  const [collection, setCollection] = useState<KnowledgeCollection | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searchWarning, setSearchWarning] = useState<string | null>(null);
  const [selected, setSelected] = useState<Citation | null>(null);
  const [answerRefs, setAnswerRefs] = useState<Citation[]>([]);
  const [mobileDocument, setMobileDocument] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useFeedback(error, message);
  const closeRename = useUnsavedChanges(renameDirty, busy);
  const abort = useRef<AbortController | null>(null);
  const loadSequence = useRef(0);
  const reload = useCallback(async () => {
    const sequence = ++loadSequence.current;
    const next = await knowledgeRequest<KnowledgeCollection>(
        "/knowledge/collections/" + collectionId,
      );
    if (sequence === loadSequence.current) setCollection(next);
  }, [collectionId]);
  useEffect(() => {
    void reload().catch((e: Error) => setError(e.message));
    return () => abort.current?.abort();
  }, [reload]);
  // 解析完成到定时派发索引之间存在间隔，此时仍需轮询，才能自动显示最终入库状态。
  const processing = collection?.sources?.some(
    (s) =>
      ["pending", "processing"].includes(s.state) ||
      ["pending", "running"].includes(s.index_status ?? "") ||
      (["ready", "partial"].includes(s.state) && !s.index_status),
  );
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => {
      void reload().catch((e: Error) => setError(e.message));
    }, 3000);
    return () => clearInterval(timer);
  }, [processing, reload]);
  const refs = useMemo(
    () => [
      ...(hits?.map((hit) => ({ ...hit, quote: hit.content })) ?? []),
      ...answerRefs,
    ],
    [hits, answerRefs],
  );
  const locate = async (ref: Citation) => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    try {
      const resolved = await resolveCitation(ref, controller.signal);
      if (!controller.signal.aborted) {
        setSelected(resolved);
        setMobileDocument(true);
      }
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "原文不可用");
    }
  };
  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await reload().catch(() =>
        setError("操作已完成，刷新状态失败，请重试刷新。"),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <PageShell
      eyebrow="知识库"
      title={collection?.name ?? "正在打开资料库…"}
      breadcrumb={[
        <Link key="kb" href="/knowledge">
          知识库
        </Link>,
        collection?.name ?? "资料",
      ]}
      description={
        collection
          ? PURPOSE_LABELS[collection.purpose] +
            " · 原文、检索结果与引用一同保留"
          : undefined
      }
      actions={
        collection && (
          <Link
            className={BUTTON_CLASS}
            href={"/projects/" + collection.upload_project_id + "/files"}
          >
            文件管理
          </Link>
        )
      }
    >
      {error && (
        <Alert
          className="mb-4"
          type="error"
          title={error}
          action={
            <Button
              size="small"
              onClick={() =>
                void reload().catch((e: Error) => setError(e.message))
              }
            >
              重试
            </Button>
          }
        />
      )}
      {message && (
        <p role="status" className="notice mb-4">
          {message}
        </p>
      )}
      {collection && (
        <>
          <details className="analysis-options mb-4">
            <summary>上传与管理资料</summary>
            <div className="p-4">
              <UploadPanel
                busy={busy}
                onUpload={async (files, archive, options, onProgress) => {
                  setBusy(true);
                  try {
                    const result = await uploadProjectFiles(
                      collection.upload_project_id,
                      files,
                      { ...options, role: options.role || null },
                      archive,
                      onProgress,
                    );
                    await reload().catch(() =>
                      setError("文件已上传，刷新状态失败，请刷新页面"),
                    );
                    return result;
                  } finally {
                    setBusy(false);
                  }
                }}
              />
              {!collection.is_project && (
                <Space className="mt-4" wrap>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      renameForm.setFieldsValue({ name: collection.name });
                      setRenameDirty(false);
                      setError(null);
                      setRenaming(true);
                    }}
                  >
                    重命名
                  </Button>
                  <Button
                    danger
                    disabled={busy}
                    onClick={() =>
                      modal.confirm({
                        title: "移除这个知识库？",
                        content: "关联项目将无法继续检索其中的资料。",
                        okText: "移除",
                        okButtonProps: { danger: true },
                        onOk: async () => {
                          try {
                            await knowledgeRequest(
                              "/knowledge/collections/" + collectionId,
                              "DELETE",
                            );
                            void toast.success("知识库已移除");
                            router.push("/knowledge");
                          } catch (e) {
                            setError(
                              e instanceof Error ? e.message : "移除失败",
                            );
                            throw e;
                          }
                        },
                      })
                    }
                  >
                    移除知识库
                  </Button>
                </Space>
              )}
              <Modal
                open={renaming}
                title="重命名知识库"
                centered
                destroyOnHidden
                mask={{ closable: false }}
                keyboard={!busy}
                closable={!busy}
                onCancel={() => closeRename(() => { setRenaming(false); setRenameDirty(false); })}
                footer={
                  <Space>
                    <Button
                      disabled={busy}
                      onClick={() => closeRename(() => { setRenaming(false); setRenameDirty(false); })}
                    >
                      取消
                    </Button>
                    <Button
                      type="primary"
                      htmlType="submit"
                      form="rename-collection"
                      loading={busy}
                    >
                      保存
                    </Button>
                  </Space>
                }
              >
                {error && <Alert className="mb-4" type="error" title={error} />}
                <Form
                  form={renameForm}
                  id="rename-collection"
                  layout="vertical"
                  disabled={busy}
                  onValuesChange={() => setRenameDirty(true)}
                  onFinish={(values: { name: string }) =>
                    void perform(async () => {
                      await knowledgeRequest(
                        "/knowledge/collections/" + collectionId,
                        "PATCH",
                        {
                          name: values.name.trim(),
                          purpose: collection.purpose,
                        },
                      );
                      setRenameDirty(false);
                      setRenaming(false);
                      void toast.success("知识库已重命名");
                    })
                  }
                >
                  <Form.Item
                    name="name"
                    label="知识库名称"
                    rules={[
                      {
                        required: true,
                        whitespace: true,
                        message: "请输入知识库名称",
                      },
                      { max: 200, message: "最多 200 字" },
                    ]}
                  >
                    <Input autoFocus maxLength={200} />
                  </Form.Item>
                </Form>
              </Modal>
            </div>
          </details>
          <div className="knowledge-index-bar">
            <span>
              {collection.embedding_configured
                ? "语义检索模型：" + collection.embedding_model
                : "语义检索未配置 · 全文检索可用"}
            </span>
            <Link href="/settings/models" className="text-violet-700">
              配置模型
            </Link>
            {collection.embedding_configured && (
              <Button
                htmlType="submit"
                disabled={busy}
                onClick={() =>
                  void perform(async () => {
                    const result = await knowledgeRequest<{
                      dimension: number;
                    }>("/knowledge/embedding/test", "POST", {});
                    setMessage("向量模型连接成功，维度 " + result.dimension);
                  })
                }
              >
                测试向量模型
              </Button>
            )}
            <Button
              htmlType="submit"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  const result = await knowledgeRequest<{
                    queued_count: number;
                  }>(
                    "/knowledge/collections/" + collectionId + "/reindex",
                    "POST",
                    {},
                  );
                  setMessage(
                    "已安排 " + result.queued_count + " 份资料重建索引",
                  );
                })
              }
            >
              重建索引
            </Button>
          </div>
          <details className="analysis-options mb-4">
            <summary>
              资料处理状态 <span>{collection.sources?.length ?? 0} 份</span>
            </summary>
            <div className="knowledge-source-list">
              {collection.sources?.map((source) => (
                <div key={source.source_id}>
                  <span className="min-w-0 flex-1">
                    <strong>{source.file_name}</strong>
                    <small>
                      {STATE_LABELS[source.state] ?? source.state} ·{" "}
                      {source.index_status === "completed"
                        ? source.semantic_ready
                          ? "全文与向量索引就绪"
                          : source.needs_reindex
                            ? "全文可用 · 请重建当前模型的向量索引"
                            : "全文索引就绪"
                        : (source.index_error ??
                          (source.index_status === "running"
                            ? "正在构建索引"
                            : "等待建立索引"))}
                    </small>
                    {source.error_message && (
                      <small className="text-rose-700">
                        {source.error_message}
                      </small>
                    )}
                  </span>
                  {["pending", "failed", "unsupported"].includes(
                    source.state,
                  ) && (
                    <Button
                      htmlType="submit"
                      disabled={busy}
                      onClick={() =>
                        void perform(() =>
                          knowledgeRequest(
                            "/knowledge/sources/" +
                              source.source_id +
                              "/process",
                            "POST",
                            {},
                          ),
                        )
                      }
                    >
                      重新处理
                    </Button>
                  )}
                  <Button
                    htmlType="submit"
                    disabled={busy}
                    onClick={() =>
                      modal.confirm({
                        title: "移除这份资料？",
                        content: "对应引用将变为不可用。",
                        okText: "移除",
                        okButtonProps: { danger: true },
                        onOk: async () => {
                          try {
                            await deleteProjectFile(
                              collection.upload_project_id,
                              source.project_file_id,
                            );
                            void toast.success("资料已移除");
                            await reload().catch(() =>
                              setError("资料已移除，刷新失败。"),
                            );
                          } catch (e) {
                            setError(
                              e instanceof Error ? e.message : "移除失败",
                            );
                            throw e;
                          }
                        },
                      })
                    }
                  >
                    移除
                  </Button>
                </div>
              ))}
            </div>
          </details>
          <div className="analysis-mobile-switch">
            <button
              aria-pressed={!mobileDocument}
              onClick={() => setMobileDocument(false)}
            >
              资料检索
            </button>
            <button
              aria-pressed={mobileDocument}
              disabled={!selected}
              onClick={() => setMobileDocument(true)}
            >
              引用原文
            </button>
          </div>
          <div
            className="analysis-split knowledge-detail-split"
            data-document={mobileDocument}
          >
            <div className="analysis-content">
              <form
                className="mb-5 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (busy || !search.trim()) return;
                  setSearchWarning(null);
                  void perform(async () => {
                    const result = await knowledgeRequest<{
                      items: SearchHit[];
                      warning?: string | null;
                    }>(
                      "/knowledge/collections/" +
                        collectionId +
                        "/search?q=" +
                        encodeURIComponent(search),
                    );
                    setHits(result.items);
                    // 模型冷启动时全文结果仍可用，明确告知本次回退，避免误以为已完成语义召回。
                    setSearchWarning(result.warning ?? null);
                  });
                }}
              >
                <Input
                  className={" min-w-0 flex-1"}
                  aria-label="搜索原文"
                  placeholder="搜索名称、条款或关键词"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  maxLength={2000}
                  required
                />
                <Button type="primary" htmlType="submit" disabled={busy}>
                  搜索
                </Button>
              </form>
              {searchWarning && (
                <p role="status" className="notice mb-4">
                  {searchWarning}
                </p>
              )}
              {hits?.length === 0 && (
                <p className="notice mb-4">当前可用原文中没有匹配内容。</p>
              )}
              {hits?.map((hit, i) => (
                <button
                  key={hit.source_id + ":" + hit.element_id + ":" + i}
                  className="knowledge-hit"
                  onClick={() => void locate({ ...hit, quote: hit.content })}
                >
                  <span>
                    {hit.file_name} · 第 {hit.page_no} 页 ↗
                  </span>
                  <p>{hit.content}</p>
                </button>
              ))}
              <QuestionPanel
                endpoint={"/knowledge/collections/" + collectionId + "/ask"}
                onLocate={(ref) => void locate(ref)}
                onCitations={setAnswerRefs}
              />
            </div>
            <aside className="analysis-document">
              {selected ? (
                <CitationViewer
                  key={selected.version_id + ":" + selected.parse_run_id}
                  selected={selected}
                  citations={[...refs, selected]}
                />
              ) : (
                <div className="empty-state">
                  <h3>从检索结果回到原文</h3>
                  <p>点击片段或回答引用，在这里核对原文件。</p>
                </div>
              )}
            </aside>
          </div>
        </>
      )}
    </PageShell>
  );
}
