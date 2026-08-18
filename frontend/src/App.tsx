import { useEffect, useState } from "react";

import { type DocMeta, type SearchResult, listAllDocuments, search } from "./api";
import { DirectoryTree } from "./components/DirectoryTree";
import { DocList } from "./components/DocList";
import { Reader } from "./components/Reader";
import { SearchBox } from "./components/SearchBox";
import { SearchResults } from "./components/SearchResults";

export default function App() {
  const [docs, setDocs] = useState<DocMeta[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dir, setDir] = useState<string | null>(null); // 树选中的目录；null = 全部
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [openDoc, setOpenDoc] = useState<{ id: number; rel_path: string } | null>(null);

  useEffect(() => {
    listAllDocuments()
      .then(setDocs)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  // 全局搜索：输入防抖 + 实时显示
  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = setTimeout(() => {
      search(query.trim())
        .then(setResults)
        .catch(() => setResults({ query, total: 0, limit: 50, offset: 0, hits: [] }))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const openDocument = (id: number, rel_path: string) => setOpenDoc({ id, rel_path });

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand">📚 本地知识库</h1>
        <SearchBox value={query} onChange={setQuery} searching={searching} />
        {results && <span className="count">命中 {results.total} 篇</span>}
      </header>
      <div className="body">
        <aside className="sidebar">
          {loadError && <div className="error">加载失败：{loadError}</div>}
          {docs && (
            <DirectoryTree
              docs={docs}
              selected={dir}
              onSelectDir={setDir}
              onOpenDoc={openDocument}
            />
          )}
        </aside>
        <section className="center">
          {results ? (
            <SearchResults results={results} onOpen={openDocument} />
          ) : docs ? (
            <DocList docs={docs} dir={dir} onOpen={openDocument} />
          ) : (
            !loadError && <div className="hint">加载文档列表…</div>
          )}
        </section>
        <main className="main">
          {openDoc ? (
            <Reader
              key={openDoc.id}
              docId={openDoc.id}
              relPath={openDoc.rel_path}
              onClose={() => setOpenDoc(null)}
              onOpen={openDocument}
            />
          ) : (
            <div className="empty">
              <p>从左侧目录或搜索选择一篇文档。</p>
              <p className="dim">
                用鼠标点击 markdown 内的相对链接 / WikiLink 可直接跳转。
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}