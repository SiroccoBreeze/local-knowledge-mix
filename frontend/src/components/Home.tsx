/** 知识库首页：入口 + 搜索 + 最近访问（不铺满文档标题）。 */

import { type DocMeta } from "../api";
import { DocRow, itemOf } from "./DocRow";

interface Props {
  docs: DocMeta[] | null;
  recentVisits: { id: number; relPath: string; ts: number }[];
  recentDocs: DocMeta[];
  onOpenDoc: (id: number, relPath: string) => void;
  onOpenSearch: () => void;
}

export function Home({ docs, recentVisits, recentDocs, onOpenDoc, onOpenSearch }: Props) {
  const visitItems = recentVisits
    .map((v) => (docs ? docs.find((d) => d.id === v.id) : undefined))
    .filter((d): d is DocMeta => d !== undefined)
    .map(itemOf);

  const recentItems = recentDocs.map(itemOf);

  return (
    <section className="home">
      <p className="home-kicker">知识库</p>
      <h1 className="home-title">{docs ? `${docs.length} 篇文档` : "…"}</h1>

      <button className="home-search" onClick={onOpenSearch}>
        <span className="home-search-text">搜索文档…</span>
        <kbd>⌘K</kbd>
      </button>

      {visitItems.length > 0 && (
        <>
          <h2 className="home-section">最近访问</h2>
          <div className="doc-list">
            {visitItems.map((it) => (
              <DocRow key={it.id} item={it} onOpen={onOpenDoc} />
            ))}
          </div>
        </>
      )}

      {recentItems.length > 0 && (
        <>
          <h2 className="home-section">最近更新</h2>
          <div className="doc-list">
            {recentItems.map((it) => (
              <DocRow key={it.id} item={it} onOpen={onOpenDoc} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}