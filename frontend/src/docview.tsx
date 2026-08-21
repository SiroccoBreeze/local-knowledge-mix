/** 文档详情数据获取 + 共享面板（Reader 与 ShareView 复用）。 */

import { useEffect, useState } from "react";

import {
  type AssetMeta,
  type DocMeta,
  type Neighbor,
  categoryOf,
  getDoc,
  getDocContent,
  getNeighbors,
  getRelatedDocuments,
  listAssets,
  rawUrl,
  type RelatedItem,
} from "./api";

export interface LinkTarget {
  id: number;
  title: string;
  rel_path: string;
}

export interface DocData {
  meta: DocMeta | null;
  content: string | null;
  linkMap: Map<string, LinkTarget>;
  assets: AssetMeta[];
  incoming: Neighbor[];
  outgoing: Neighbor[];
  error: string | null;
}

export function useDocData(docId: number): DocData {
  const [meta, setMeta] = useState<DocMeta | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [linkMap, setLinkMap] = useState<Map<string, LinkTarget>>(new Map());
  const [assets, setAssets] = useState<AssetMeta[]>([]);
  const [incoming, setIncoming] = useState<Neighbor[]>([]);
  const [outgoing, setOutgoing] = useState<Neighbor[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setMeta(null);
    setContent(null);
    setError(null);
    setLinkMap(new Map());
    setAssets([]);
    setIncoming([]);
    setOutgoing([]);

    getDoc(docId)
      .then((m) => alive && setMeta(m))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    getDocContent(docId)
      .then((t) => alive && setContent(t))
      .catch(() => alive && setError("读取正文失败"));
    getNeighbors(docId)
      .then((nb) => {
        if (!alive) return;
        setIncoming(nb.incoming);
        setOutgoing(nb.outgoing);
        const map = new Map<string, LinkTarget>();
        for (const out of nb.outgoing) {
          // 相对链接用原文 target（markdown href 一致），wiki 用 [[target]]
          map.set(out.target, { id: out.doc_id, title: out.title, rel_path: out.rel_path });
        }
        setLinkMap(map);
      })
      .catch(() => {
        /* 链接解析失败不影响阅读 */
      });
    listAssets(docId)
      .then((a) => alive && setAssets(a))
      .catch(() => {
        /* 附件面板失败不影响阅读 */
      });

    return () => {
      alive = false;
    };
  }, [docId]);

  return { meta, content, linkMap, assets, incoming, outgoing, error };
}

export function fmtDate(mtimeNs: number): string {
  const d = new Date(mtimeNs / 1_000_000);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

export function AssetPanel({ assets }: { assets: AssetMeta[] }) {
  const images = assets.filter((a) => a.mime_type.startsWith("image/") && a.status === "indexed");
  const files = assets.filter((a) => !a.mime_type.startsWith("image/"));

  const label = (t: string) => (
    <h3 className="mb-3 mt-7 text-[11px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
      {t}
    </h3>
  );

  return (
    <section className="mt-10 border-t border-zinc-200/80 pt-2 dark:border-zinc-800">
      {label(`图片（${images.length}）`)}
      {images.length === 0 ? (
        <p className="text-sm text-zinc-400 dark:text-zinc-500">无</p>
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {images.map((a) => (
            <a key={a.id} href={rawUrl(a.relative_path)} target="_blank" rel="noreferrer" title={a.relative_path}>
              <img
                src={rawUrl(a.relative_path)}
                alt={a.filename}
                loading="lazy"
                className="aspect-square w-full rounded-lg border border-zinc-200 object-cover transition-transform duration-200 hover:scale-[1.02] dark:border-zinc-800"
              />
            </a>
          ))}
        </div>
      )}
      {label("附件")}
      {files.length === 0 ? (
        <p className="text-sm text-zinc-400 dark:text-zinc-500">无</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {files.map((a) => (
            <li key={a.id} className="truncate">
              <a href={rawUrl(a.relative_path)} target="_blank" rel="noreferrer" className="text-zinc-700 hover:underline dark:text-zinc-200">
                📎 {a.filename}
              </a>
              <span className="ml-2 text-xs text-zinc-400">
                {a.extension} · {(a.size / 1024).toFixed(1)} KB
                {a.status !== "indexed" ? " · 缺失" : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface LinkPanelsProps {
  outgoing: Neighbor[];
  incoming: Neighbor[];
  onOpen: (id: number, relPath: string) => void;
}

export function LinkPanels({ outgoing, incoming, onOpen }: LinkPanelsProps) {
  const section = (title: string, rows: Neighbor[]) => (
    <>
      <h3 className="mb-3 mt-7 text-[11px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
        {title}（{rows.length}）
      </h3>
      {rows.length === 0 ? (
        <p className="text-sm text-zinc-400 dark:text-zinc-500">无</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {rows.map((nb, i) => (
            <button
              key={i}
              onClick={() => onOpen(nb.doc_id, nb.rel_path)}
              className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-[13px] text-zinc-700 transition-colors hover:border-zinc-400 hover:text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:border-zinc-500"
            >
              {nb.title || nb.rel_path}
              <span className="ml-1 text-[11px] text-zinc-400">{nb.kind}</span>
            </button>
          ))}
        </div>
      )}
    </>
  );

  return (
    <section className="mt-10 border-t border-zinc-200/80 pt-2 dark:border-zinc-800">
      {section("出链", outgoing)}
      {section("入链", incoming)}
    </section>
  );
}

export function RelatedDocs({
  items,
  loading,
  error,
  onOpen,
}: {
  items: RelatedItem[];
  loading: boolean;
  error: boolean;
  onOpen: (id: number, relPath: string) => void;
}) {
  if (loading) {
    return (
      <section className="mt-10 border-t border-zinc-200/80 pt-4 dark:border-zinc-800">
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
          相关文档
        </h3>
        <p className="text-sm text-zinc-400 dark:text-zinc-500">加载相关文档…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section className="mt-10 border-t border-zinc-200/80 pt-4 dark:border-zinc-800">
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
          相关文档
        </h3>
        <p className="text-sm text-zinc-400 dark:text-zinc-500">相关文档暂时不可用</p>
      </section>
    );
  }
  if (items.length === 0) {
    return (
      <section className="mt-10 border-t border-zinc-200/80 pt-4 dark:border-zinc-800">
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
          相关文档
        </h3>
        <p className="text-sm text-zinc-400 dark:text-zinc-500">暂未找到足够相关的文档</p>
      </section>
    );
  }
  return (
    <section className="mt-10 border-t border-zinc-200/80 pt-4 dark:border-zinc-800">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
        相关文档（{items.length}）
      </h3>
      <div className="space-y-1">
        {items.map((it) => (
          <button
            key={it.doc_id}
            onClick={() => onOpen(it.doc_id, it.rel_path)}
            className="block w-full rounded-lg px-3 py-2 text-left transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800/70"
          >
            <span className="block text-[14.5px] font-medium text-zinc-800 dark:text-zinc-100">
              {it.title}
            </span>
            <span className="mt-0.5 block truncate font-mono text-[12px] text-zinc-400 dark:text-zinc-500">
              {it.rel_path} · 相关度 {it.score.toFixed(2)}
            </span>
            {it.reasons && it.reasons.length > 0 && (
              <span className="mt-0.5 block text-[12px] text-amber-600 dark:text-amber-400">
                {it.reasons.slice(0, 2).map((r) => RELATED_REASON_LABELS[r] ?? r).join(" · ")}
              </span>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

export function useRelatedDocuments(docId: number): {
  items: RelatedItem[];
  loading: boolean;
  error: boolean;
} {
  const [items, setItems] = useState<RelatedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    setItems([]);
    setLoading(true);
    setError(false);
    getRelatedDocuments(docId)
      .then((r) => {
        if (!alive) return;
        setItems(r.items);
        setLoading(false);
      })
      .catch(() => {
        if (!alive) return;
        setLoading(false);
        setError(true);
      });
    return () => {
      alive = false;
    };
  }, [docId]);

  return { items, loading, error };
}

const RELATED_REASON_LABELS: Record<string, string> = {
  linked: "有链接关系",
  same_directory: "同目录",
  shared_tag: "共同标签",
  title_similarity: "标题相似",
  heading_similarity: "章节相似",
  term_similarity: "内容相关",
};

export function fmtCnDate(value: string | number): string {
  let d: Date;
  const raw = String(value);
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(raw);
  if (m) d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  else if (typeof value === "number") d = new Date(value / 1_000_000);
  else d = new Date(raw);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

export interface DocHeaderInfo {
  relPath: string;
  title: string;
  category: string;
  modifiedAt: string;
  created?: string; // 人类化日期（取自 frontmatter.created，缺省用 mtime）
  knowledge?: string | null; // resolved→已解决 / 未解决；status 字符串透传
  tags: string[];
}

export function docHeaderOf(meta: DocMeta): DocHeaderInfo {
  const fm = meta.frontmatter ?? {};
  const tagsRaw = fm.tags;
  const tags =
    Array.isArray(tagsRaw) ? tagsRaw.map(String) : typeof tagsRaw === "string" ? [tagsRaw] : [];
  let knowledge: string | null = null;
  if (typeof fm.resolved === "boolean") knowledge = fm.resolved ? "已解决" : "未解决";
  else if (typeof fm.status === "string" && fm.status.trim()) knowledge = fm.status.trim();
  const createdRaw = typeof fm.created === "string" ? fm.created : undefined;
  return {
    relPath: meta.rel_path,
    title: meta.title || meta.rel_path,
    category: categoryOf(meta.rel_path),
    modifiedAt: fmtDate(meta.mtime_ns),
    created: createdRaw ? fmtCnDate(createdRaw) : undefined,
    knowledge,
    tags,
  };
}