/** 文档详情数据获取 + 共享面板（Reader 与 ShareView 复用）。 */

import { useEffect, useMemo, useState } from "react";

import {
  type AssetMeta,
  type DocMeta,
  type Neighbor,
  categoryOf,
  dirOf,
  getDoc,
  getDocContent,
  getNeighbors,
  listAssets,
  rawUrl,
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

export function fmtTime(mtimeNs: number): string {
  const d = new Date(mtimeNs / 1_000_000);
  return Number.isNaN(d.getTime())
    ? "—"
    : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate()
      ).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(
        d.getMinutes()
      ).padStart(2, "0")}`;
}

export function AssetPanel({ assets }: { assets: AssetMeta[] }) {
  const images = assets.filter((a) => a.mime_type.startsWith("image/") && a.status === "indexed");
  const files = assets.filter((a) => !a.mime_type.startsWith("image/"));

  return (
    <section className="panel">
      <h3>图片（{images.length}）</h3>
      {images.length === 0 ? (
        <p className="dim">无</p>
      ) : (
        <div className="asset-images">
          {images.map((a) => (
            <a key={a.id} href={rawUrl(a.relative_path)} target="_blank" rel="noreferrer" title={a.relative_path}>
              <img src={rawUrl(a.relative_path)} alt={a.filename} loading="lazy" />
            </a>
          ))}
        </div>
      )}
      <h3>附件（{files.length + assets.filter((a) => a.status !== "indexed").length}）</h3>
      {files.length === 0 ? (
        <p className="dim">无</p>
      ) : (
        <ul className="asset-files">
          {files.map((a) => (
            <li key={a.id}>
              <a href={rawUrl(a.relative_path)} target="_blank" rel="noreferrer">
                📎 {a.filename}
              </a>
              <span className="dim">
                {" "}
                · {a.extension} · {(a.size / 1024).toFixed(1)} KB ·{" "}
                {a.status === "indexed" ? a.sha256.slice(0, 8) : "文件缺失"}
              </span>
            </li>
          ))}
          {assets
            .filter((a) => a.status !== "indexed")
            .map((a) => (
              <li key={`missing-${a.id}`} className="dim">
                ⚠ 缺失：{a.filename}（{a.relative_path}）
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
  return (
    <section className="panel">
      <h3>出链（{outgoing.length}）</h3>
      {outgoing.length === 0 ? (
        <p className="dim">无</p>
      ) : (
        <ul className="link-chips">
          {outgoing.map((nb, i) => (
            <li key={i}>
              <button className="chip" onClick={() => onOpen(nb.doc_id, nb.rel_path)}>
                {nb.title || nb.rel_path}
                <span className="chip-kind">{nb.kind}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <h3>入链（{incoming.length}）</h3>
      {incoming.length === 0 ? (
        <p className="dim">无</p>
      ) : (
        <ul className="link-chips">
          {incoming.map((nb, i) => (
            <li key={i}>
              <button className="chip" onClick={() => onOpen(nb.doc_id, nb.rel_path)}>
                {nb.title || nb.rel_path}
                <span className="chip-kind">{nb.kind}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function RelatedDocs({
  docs,
  currentRel,
  onOpen,
}: {
  docs: DocMeta[] | null;
  currentRel: string;
  onOpen: (id: number, relPath: string) => void;
}) {
  const related = useMemo(() => {
    if (!docs) return [];
    const dir = dirOf(currentRel);
    return docs
      .filter((d) => d.rel_path !== currentRel && dirOf(d.rel_path) === dir)
      .sort((a, b) => b.mtime_ns - a.mtime_ns)
      .slice(0, 12);
  }, [docs, currentRel]);

  if (related.length === 0) return null;
  return (
    <section className="panel">
      <h3>相关文档（同目录 · {related.length}）</h3>
      <ul className="link-chips">
        {related.map((d) => (
          <li key={d.id}>
            <button className="chip" onClick={() => onOpen(d.id, d.rel_path)}>
              {d.title || d.rel_path}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export interface DocHeaderInfo {
  relPath: string;
  title: string;
  category: string;
  modifiedAt: string;
}

export function docHeaderOf(meta: DocMeta): DocHeaderInfo {
  return {
    relPath: meta.rel_path,
    title: meta.title || meta.rel_path,
    category: categoryOf(meta.rel_path),
    modifiedAt: fmtTime(meta.mtime_ns),
  };
}