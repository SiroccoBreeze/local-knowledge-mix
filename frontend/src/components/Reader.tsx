import { useEffect, useMemo, useRef, useState } from "react";

import { type DocMeta } from "../api";
import {
  AssetPanel,
  LinkPanels,
  RelatedDocs,
  docHeaderOf,
  useDocData,
} from "../docview";
import {
  handleBodyClick,
  preprocessWiki,
  renderMarkdown,
  stripFrontmatter,
} from "../md";

interface Props {
  docId: number;
  onClose: () => void;
  onOpen: (id: number, relPath: string) => void;
  docs: DocMeta[] | null;
  favorite: boolean;
  onToggleFavorite: (id: number) => void;
  onShare: (id: number) => void;
}

export function Reader({ docId, onClose, onOpen, docs, favorite, onToggleFavorite, onShare }: Props) {
  const { meta, content, linkMap, assets, incoming, outgoing, error } = useDocData(docId);
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null);
  const relPath = meta?.rel_path ?? "";
  const header = meta ? docHeaderOf(meta) : null;

  const html = useMemo(() => {
    if (content === null) return "";
    return renderMarkdown({
      content: preprocessWiki(stripFrontmatter(content)),
      relPath,
      linkMap,
    });
  }, [content, relPath, linkMap]);

  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setZoom(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoom]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const hit = handleBodyClick(e);
    if (!hit) return;
    if (hit.said === "navigate" && hit.id !== undefined) {
      onOpen(hit.id, hit.relPath ?? "");
    } else if (hit.said === "copy") {
      navigator.clipboard?.writeText(hit.text ?? "").then(() => {
        const btn = (e.target as HTMLElement).closest("button.code-copy");
        if (btn) {
          const prev = btn.textContent;
          btn.textContent = "已复制 ✓";
          setTimeout(() => (btn.textContent = prev), 1200);
        }
      }, () => undefined);
    } else if (hit.said === "zoom" && hit.src) {
      setZoom({ src: hit.src, alt: hit.alt ?? "" });
    }
  };

  return (
    <article className="reader">
      {error ? (
        <div className="list-empty">读取失败:{error}</div>
      ) : meta === null ? (
        <div className="list-empty">加载中…</div>
      ) : (
        <>
          <header className="doc-head">
            <h1 className="doc-title">{header?.title}</h1>
            <div className="doc-meta">
              <span className="doc-collection">{header?.category}</span>
              <span className="separator">·</span>
              <span className="doc-time">更新于 {header?.modifiedAt}</span>
            </div>
            {header && header.tags.length > 0 && (
              <div className="doc-tags">
                {header.tags.map((t) => (
                  <span key={t} className="tag">
                    {t}
                  </span>
                ))}
              </div>
            )}
            <div className="doc-actions">
              <button className="text-btn" onClick={() => onShare(docId)}>
                🔗 分享
              </button>
              <button
                className={`text-btn ${favorite ? "fav-on" : ""}`}
                onClick={() => onToggleFavorite(docId)}
                title="收藏"
              >
                {favorite ? "★ 已收藏" : "☆ 收藏"}
              </button>
              <button className="text-btn" onClick={onClose}>
                ← 返回
              </button>
            </div>
            <details className="doc-info">
              <summary>Document Info</summary>
              <dl>
                <dt>id</dt>
                <dd>{meta.id}</dd>
                <dt>路径</dt>
                <dd>{meta.rel_path}</dd>
                <dt>状态</dt>
                <dd>{meta.status}</dd>
                <dt>sha256</dt>
                <dd>{meta.sha256}</dd>
                <dt>大小</dt>
                <dd>{(meta.size / 1024).toFixed(1)} KB</dd>
                <dt>mtime</dt>
                <dd>{meta.mtime_ns}</dd>
                <dt>字数</dt>
                <dd>{meta.word_count}</dd>
              </dl>
            </details>
          </header>

          <div
            ref={containerRef}
            className="markdown-body"
            dangerouslySetInnerHTML={{ __html: html }}
            onClick={handleClick}
          />

          {assets.length > 0 && <AssetPanel assets={assets} />}
          {(outgoing.length > 0 || incoming.length > 0) && (
            <LinkPanels outgoing={outgoing} incoming={incoming} onOpen={onOpen} />
          )}
          <RelatedDocs docs={docs} currentRel={relPath} onOpen={onOpen} />
        </>
      )}

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom.src} alt={zoom.alt} />
          {zoom.alt && <div className="lightbox-caption">{zoom.alt}</div>}
        </div>
      )}
    </article>
  );
}