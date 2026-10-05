"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageShell } from "@/components/PageShell";
import { Icon } from "@/components/Icon";
import { BUTTON_CLASS, INPUT_CLASS, PRIMARY_BUTTON_CLASS, SELECT_CLASS } from "@/components/ui";
import { knowledgeRequest } from "@/lib/api/knowledge";
import { PURPOSE_LABELS, type KnowledgeCollection } from "@/types/knowledge";

export function KnowledgeCollections() {
  const [items, setItems] = useState<KnowledgeCollection[] | null>(null);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("company");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => setItems((await knowledgeRequest<{ items: KnowledgeCollection[] }>("/knowledge/collections")).items), []);
  useEffect(() => { void reload().catch((e: Error) => setError(e.message)); }, [reload]);
  return <PageShell eyebrow="知识库" title="资料各有所属，依据随时可查" description="按用途整理招标材料、企业资料与历史标书。将需要的知识库关联到项目，即可在问答中查阅。"
    actions={<button className={PRIMARY_BUTTON_CLASS} onClick={() => setCreating(!creating)}><Icon name="plus" size={16} />新建知识库</button>}>
    {error && <p role="alert" className="notice mb-4">{error}</p>}
    {creating && <form className="knowledge-create" onSubmit={async (event) => {
      event.preventDefault(); setBusy(true); setError(null);
      try { await knowledgeRequest("/knowledge/collections", "POST", { name, purpose }); setName(""); setCreating(false); await reload(); }
      catch (e) { setError(e instanceof Error ? e.message : "创建失败"); } finally { setBusy(false); }
    }}>
      <label>知识库名称<input autoFocus className={INPUT_CLASS} required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：公司资质与证明材料" /></label>
      <label>资料用途<select className={SELECT_CLASS} value={purpose} onChange={(e) => setPurpose(e.target.value)}>{Object.entries(PURPOSE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <button className={PRIMARY_BUTTON_CLASS} disabled={busy}>{busy ? "创建中…" : "创建"}</button><button type="button" className={BUTTON_CLASS} onClick={() => setCreating(false)}>取消</button>
    </form>}
    {items === null ? <p role="status" className="p-8 text-slate-500">正在加载知识库…</p> : !items.length ? <div className="empty-state"><Icon name="book" size={30} /><h2>从一组可靠的资料开始</h2><p>新建知识库后上传资料。每份资料都会保留原文与来源版本。</p></div>
      : <div className="knowledge-grid">{items.map((item) => <Link key={item.id} href={"/knowledge/" + item.id} className="knowledge-card">
        <div className="flex items-center gap-3"><span className="knowledge-card-icon"><Icon name={item.is_project ? "folder" : "book"} size={23} /></span><span className="text-xs text-slate-500">{item.is_project ? "项目资料库" : PURPOSE_LABELS[item.purpose]}</span></div>
        <h2>{item.name}</h2><div className="flex items-center justify-between text-sm text-slate-500"><span>{item.file_count} 份资料</span><span className="text-violet-700">打开资料库 ↗</span></div>
      </Link>)}</div>}
  </PageShell>;
}
