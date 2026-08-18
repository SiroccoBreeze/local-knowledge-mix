/** /share/{id} — 本地只读分享页（无侧栏/列表，仅正文 + 资产 + 链接）。 */

import { useMemo, useState } from "react";

import { AssetPanel, LinkPanels, docHeaderOf, useDocData } from "../docview";
import { preprocessWiki, renderMarkdown } from "./Reader";

interface Props {
  docId: number;
  onChange?: (id: number) => void;
}

export function ShareView({ docId, onChange }: Props) {
  const [cur, setCur] = useState(docId);
  const { meta, content, linkMap, assets, incoming, outgoing, error } = useDocData(cur);
  const relPath = meta?.rel_path ?? "";

  const navigate = (id: number, relPath: string) => {
    const next = { id, relPath };
    setCur(next.id);
    if (onChange) onChange(next.id);
    try {
      window.history.pushState({}, "", `/share/${next.id}`);
    } catch {
      /* 本地文件/旧浏览器降级：仅内部切换 */
    }
  };

  const html = useMemo(
    () => (content !== null ? renderMarkdown({ content, relPath, linkMap }) : ""),
    [content, relPath, linkMap]
  );

  const header = meta ? docHeaderOf(meta) : null;

  return (
    <article className="reader share-reader">
      <header className="reader-header share-header">
        <span className="share-badge">🔗 分享</span>
        <div>
          {header && <h1 className="reader-title">{header.title}</h1>}
          <div className="reader-sub">
            {header && <span className="reader-category">{header.category}</span>}
            <span className="reader-path" title={relPath}>
              {relPath}
            </span>
            {header && <span className="reader-time">修改于 {header.modifiedAt}</span>}
          </div>
        </div>
        <a className="close" href="/" title="回到知识库">
          回到知识库
        </a>
      </header>

      {error ? (
        <div className="error">文档不存在或不可用：{error}</div>
      ) : content === null ? (
        <div className="hint">加载中…</div>
      ) : (
        <>
          <div
            className="markdown-body"
            dangerouslySetInnerHTML={{ __html: html }}
            onClick={(e) => {
              const target = (e.target as HTMLElement).closest(
                "a[data-open]"
              ) as HTMLAnchorElement | null;
              if (!target) return;
              e.preventDefault();
              const id = Number(target.dataset.open);
              if (Number.isFinite(id)) navigate(id, target.dataset.path ?? "");
            }}
          />
          <AssetPanel assets={assets} />
          <LinkPanels outgoing={outgoing} incoming={incoming} onOpen={navigate} />
        </>
      )}
      <footer className="share-footer dim">
        由本地知识库生成的只读分享页 · Markdown 原文与文件永不离开 raw/
      </footer>
    </article>
  );
}

export { preprocessWiki };