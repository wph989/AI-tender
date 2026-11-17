"use client";
import { Alert, Button, Input } from "antd";
import { useEffect, useState } from "react";
import { ModuleMarkdown } from "./ModuleMarkdown";
import { knowledgeRequest } from "@/lib/api/knowledge";
import type { Citation, KnowledgeAnswer } from "@/types/knowledge";

export function QuestionPanel({
  endpoint,
  collectionIds = [],
  onLocate,
  onCitations,
}: {
  endpoint: string;
  collectionIds?: number[];
  onLocate: (ref: Citation) => void;
  onCitations: (refs: Citation[]) => void;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [id, setId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [pollRetry, setPollRetry] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (id === null) return;
    setBusy(true);
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await knowledgeRequest<KnowledgeAnswer>(
          "/knowledge/answers/" + id,
        );
        if (!alive) return;
        setAnswer(result);
        onCitations(
          result.items.flatMap((item) =>
            item.values.flatMap((value) => value.citations),
          ),
        );
        if (["pending", "running"].includes(result.status))
          timer = setTimeout(poll, 2500);
        else setBusy(false);
      } catch (e) {
        if (alive) {
          setError(e instanceof Error ? e.message : "问答加载失败");
          setBusy(false);
        }
      }
    };
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id, onCitations, pollRetry]);

  return (
    <section className="question-panel">
      <h2 className="mb-2 text-lg font-semibold">查条款，核对关联条件</h2>
      <p className="mb-4 text-sm text-slate-500">
        回答附带原文依据。需要完整要求清单时，请查看全文分析报告。
      </p>
      <form
        className="flex gap-2"
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy || !question.trim()) return;
          setBusy(true);
          setError(null);
          setAnswer(null);
          setId(null);
          onCitations([]);
          try {
            const result = await knowledgeRequest<{ id: number }>(
              endpoint,
              "POST",
              { question: question.trim(), collection_ids: collectionIds },
            );
            setId(result.id);
          } catch (e) {
            setError(e instanceof Error ? e.message : "提问失败");
            setBusy(false);
          }
        }}
      >
        <Input
          disabled={busy}
          aria-label="输入资料问题"
          className={" min-w-0 flex-1"}
          placeholder="资格条件分别需要哪些证明？"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={2000}
          required
        />
        <Button type="primary" htmlType="submit" disabled={busy}>
          {busy ? "检索中…" : "提问"}
        </Button>
      </form>
      {error && (
        <Alert
          className="mt-3"
          type="error"
          showIcon
          title={error}
          action={
            id !== null && (
              <Button
                size="small"
                onClick={() => {
                  setError(null);
                  setPollRetry((n) => n + 1);
                }}
              >
                重试读取回答
              </Button>
            )
          }
        />
      )}
      {answer?.error_message && (
        <p role="alert" className="notice mt-3">
          {answer.error_message}
        </p>
      )}
      {answer?.status === "completed" && (
        <div className="mt-4">
          <p className="mb-3 text-xs text-slate-500">
            {answer.snapshot.mode === "hybrid" ? "全文与语义检索" : "全文检索"}
            {answer.snapshot.graph_used ? " · 已结合条款关联" : ""}
          </p>
          {answer.snapshot.warning && (
            <p className="notice mb-3">{answer.snapshot.warning}</p>
          )}
          {answer.items.length ? (
            <ModuleMarkdown items={answer.items} onLocate={onLocate} />
          ) : (
            <p className="notice">当前可用材料中未找到足够依据。</p>
          )}
          {answer.relations.length > 0 && (
            <details className="mt-4">
              <summary>查看条款关联依据（{answer.relations.length}）</summary>
              {answer.relations.map((r, i) => (
                <div
                  key={i}
                  className="mt-3 rounded-lg border border-slate-200 p-3 text-sm"
                >
                  <p>
                    {r.subject} → {r.predicate} → {r.object}
                  </p>
                  <p className="text-slate-500">
                    {r.scope} {r.condition}
                  </p>
                  {r.citations.map((ref, j) => (
                    <button
                      key={j}
                      className="mr-3 mt-2 text-sky-700"
                      onClick={() => onLocate(ref)}
                    >
                      {ref.file_name} · 第 {ref.page_no} 页 ↗
                    </button>
                  ))}
                </div>
              ))}
            </details>
          )}
        </div>
      )}
    </section>
  );
}
