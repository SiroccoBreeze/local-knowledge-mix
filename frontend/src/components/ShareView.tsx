/** /share/{id} — 本地只读分享页（导航/搜索之外：仅文档 + 资产 + 链接）。 */

import { useEffect, useMemo, useState } from "react";

import { docHeaderOf, useDocData } from "../docview";
import { AssetPanel, LinkPanels } from "../docview";
import { handleBodyClick, preprocessWiki, renderMarkdown, stripFrontmatter } from "../md";

interface Props {
  docId: number;
}

export function ShareView({ docId }: Props) {
  const [cur, setCur] = useState(docId);
  const { meta, content, linkMap, assets, incoming, outgoing, error } = useDocData(cur);
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null);
  const relPath = meta?.rel_path ?? "";
  const header = meta ? docHeaderOf(meta) : null;

  // 浏览器前进/后退（popstate 更新 docId prop）时保持内部状态同步
  useEffect(() => setCur(docId), [docId]);

  const navigate = (id: number) => {
    setCur(id);
    try {
      window.history.pushState({}, "", `/share/${id}`);
    } catch {
      /* 本地文件/旧浏览器降级 */
    }
  };

  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setZoom(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoom]);

  const html = useMemo(() => {
    if (content === null) return "";
    return renderMarkdown({
      content: preprocessWiki(stripFrontmatter(content)),
      relPath,
      linkMap,
    });
  }, [content, relPath, linkMap]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const hit = handleBodyClick(e);
    if (!hit) return;
    if (hit.said === "navigate" && hit.id !== undefined) navigate(hit.id);
    else if (hit.said === "zoom" && hit.src) setZoom({ src: hit.src, alt: hit.alt ?? "" });
    else if (hit.said === "copy") {
      navigator.clipboard?.writeText(hit.text ?? "").then(() => {
        const btn = (e.target as HTMLElement).closest("button.code-copy");
        if (btn) {
          const prev = btn.textContent;
          btn.textContent = "已复制 ✓";
          setTimeout(() => (btn.textContent = prev), 1200);
        }
      }, () => undefined);
    }
  };

  return (
    <article className="reader">
      <header className="doc-head">
        <div className="doc-meta share-note">
          <span className="share-badge">🔗 分享页</span>
          <a className="text-btn" href="/">
            回到知识库 →
          </a>
        </div>
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
      </header>

      {error ? (
        <div className="list-empty">文档不存在或不可用：{error}</div>
      ) : content === null ? (
        <div className="list-empty">加载中…</div>
      ) : (
        <>
          <div
            className="markdown-body"
            dangerouslySetInnerHTML={{ __html: html }}
            onClick={handleClick}
          />
          {assets.length > 0 && <AssetPanel assets={assets} />}
          {(outgoing.length > 0 || incoming.length > 0) && (
            <LinkPanels outgoing={outgoing} incoming={incoming} onOpen={(id) => navigate(id)} />
          )}
        </>
      )}
      <footer className="share-footer dim">本地只读分享 · Markdown 原文与文件永不离开 raw/</footer>

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom.src} alt={zoom.alt} />
          {zoom.alt && <div className="lightbox-caption">{zoom.alt}</div>}
        </div>
      )}
    </article>
  );
}