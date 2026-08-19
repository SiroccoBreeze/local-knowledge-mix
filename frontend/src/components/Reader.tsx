import { useEffect, useMemo, useRef, useState } from "react";

import { type DocMeta } from "../api";
import { AssetPanel, LinkPanels, RelatedDocs, docHeaderOf, useDocData } from "../docview";
import { dedupeTitle, handleBodyClick, preprocessWiki, renderMarkdown, stripFrontmatter } from "../md";

interface Props {
  docId: number;
  onBack: () => void;
  onOpen: (id: number, relPath: string) => void;
  docs: DocMeta[] | null;
  favorite: boolean;
  onToggleFavorite: (id: number) => void;
}

export function Reader({ docId, onBack, onOpen, docs, favorite, onToggleFavorite }: Props) {
  const { meta, content, linkMap, assets, incoming, outgoing, error } = useDocData(docId);
  const [moreOpen, setMoreOpen] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const relPath = meta?.rel_path ?? "";
  const header = meta ? docHeaderOf(meta) : null;

  const html = useMemo(() => {
    if (content === null || header === null) return "";
    let h = renderMarkdown({
      content: preprocessWiki(stripFrontmatter(content)),
      relPath,
      linkMap,
    });
    h = dedupeTitle(h, header.title);
    return h;
  }, [content, relPath, linkMap, header]);

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

  const share = () => {
    const url = `${window.location.origin}/share/${docId}`;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url);
    }
    window.location.href = url;
  };

  return (
    <article className="reader">
      {error ? (
        <div className="list-empty">读取失败：{error}</div>
      ) : meta === null || header === null ? (
        <div className="list-empty">加载中…</div>
      ) : (
        <>
          <header className="doc-head">
            <div className="doc-topline">
              <button className="crumb" onClick={onBack}>
                ← 返回
              </button>
              <div className="topline-actions">
                <button className="text-btn" onClick={share}>
                  Share
                </button>
                <div className="menu-wrap">
                  <button
                    className="text-btn"
                    onClick={() => {
                      setMoreOpen((v) => !v);
                      setShowInfo(false);
                    }}
                  >
                    More ···
                  </button>
                  {moreOpen && (
                    <div className="menu" onMouseLeave={() => setMoreOpen(false)}>
                      <button
                        onClick={() => {
                          setShowInfo((v) => !v);
                          setMoreOpen(false);
                        }}
                      >
                        Document Info
                      </button>
                      <button
                        onClick={() => {
                          onToggleFavorite(docId);
                          setMoreOpen(false);
                        }}
                      >
                        {favorite ? "取消收藏" : "收藏"}
                      </button>
                      <button
                        onClick={() => {
                          navigator.clipboard?.writeText(relPath);
                          setMoreOpen(false);
                        }}
                      >
                        复制路径
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <h1 className="doc-title">{header.title}</h1>
            <div className="doc-meta">
              <span className="doc-collection">{header.category}</span>
              <span className="separator">·</span>
              <span className="doc-time">{header.modifiedAt}</span>
              {header.tags.length > 0 && (
                <>
                  <span className="separator">·</span>
                  <span className="doc-tags-inline">
                    {header.tags.slice(0, 4).map((t) => (
                      <span key={t} className="meta-tag">
                        #{t}
                      </span>
                    ))}
                  </span>
                </>
              )}
            </div>

            {showInfo && (
              <dl className="doc-info">
                <dt>ID</dt>
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
            )}
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