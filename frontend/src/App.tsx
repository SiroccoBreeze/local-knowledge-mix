import { useEffect, useMemo, useRef, useState } from "react";

import { listAllDocuments, search, type DocMeta, type SearchResult } from "./api";
import { DocListView, itemOf } from "./components/DocListView";
import { Navigation, type NavTarget } from "./components/Navigation";
import { Reader } from "./components/Reader";
import { SearchResults } from "./components/SearchResults";
import { ShareView } from "./components/ShareView";

type View =
  | { kind: "home" }
  | { kind: "list"; nav: NavTarget }
  | { kind: "search"; q: string; results: SearchResult }
  | { kind: "reader"; id: number; relPath: string }
  | { kind: "share"; id: number };

const FAV_KEY = "lk:favorites";

function loadFavorites(): Set<number> {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw).map(Number));
  } catch {
    return new Set();
  }
}

function shareIdFrom(path: string): number | null {
  const m = /^\/share\/(\d+)\/?$/.exec(path);
  return m ? Number(m[1]) : null;
}

export default function App() {
  const [docs, setDocs] = useState<DocMeta[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<View>({ kind: "home" });
  const [query, setQuery] = useState("");
  const [favorites, setFavorites] = useState<Set<number>>(loadFavorites);
  const [showMore, setShowMore] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  // ------- 数据 -------
  useEffect(() => {
    refetch();
  }, []);

  const refetch = () => {
    listAllDocuments()
      .then(setDocs)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  };

  // ------- 路由：/share/{id} -------
  const [shareId, setShareId] = useState<number | null>(() => shareIdFrom(window.location.pathname));
  useEffect(() => {
    const onPop = () => {
      const sid = shareIdFrom(window.location.pathname);
      setShareId(sid);
      if (sid === null && view.kind !== "share") setView({ kind: "home" });
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (shareId !== null) setView({ kind: "share", id: shareId });
  }, [shareId]);

  if (view.kind === "share") {
    return (
      <div className="app share-mode">
        <div className="topbar">
          <span className="brand">📚 本地知识库</span>
          <span className="topbar-spacer" />
        </div>
        <div className="share-page">
          <ShareView docId={view.id} />
        </div>
      </div>
    );
  }

  // ------- 搜索 -------
  const runSearch = (q: string) => {
    if (!q.trim()) {
      setView({ kind: "home" });
      setQuery("");
      return;
    }
    search(q.trim(), 50)
      .then((results) => {
        setView({ kind: "search", q: q.trim(), results });
      })
      .catch(() =>
        setView({
          kind: "search",
          q: q.trim(),
          results: { query: q, total: 0, limit: 50, offset: 0, hits: [] },
        })
      );
  };

  // Ctrl+K 聚焦搜索
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ------- 收藏 -------
  const toggleFavorite = (id: number) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
      } catch {
        /* 隐私模式下降级 */
      }
      return next;
    });
  };

  const shareDoc = (id: number) => {
    const url = `${window.location.origin}/share/${id}`;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(() => (window.location.href = url), () => (window.location.href = url));
    } else {
      window.location.href = url;
    }
  };

  const openDoc = (id: number, relPath: string) => {
    setView({ kind: "reader", id, relPath });
    document.getElementById("main-scroll")?.scrollTo({ top: 0 });
  };

  // ------- 列表视图内容 -------
  const listContent = useMemo(() => {
    if (docs === null) return { items: [] as ReturnType<typeof itemOf>[], empty: "", recent: false };
    if (view.kind !== "list") return { items: [], empty: "", recent: false };

    if (view.nav.kind === "all") {
      return {
        items: docs.map(itemOf).sort((a, b) => b.modifiedAt - a.modifiedAt),
        empty: "还没有文档。",
        recent: false,
      };
    }
    if (view.nav.kind === "recent") {
      return {
        items: docs.map(itemOf).sort((a, b) => b.modifiedAt - a.modifiedAt).slice(0, 30),
        empty: "还没有文档。",
        recent: true,
      };
    }
    if (view.nav.kind === "favorites") {
      return {
        items: docs
          .filter((d) => favorites.has(d.id))
          .map(itemOf)
          .sort((a, b) => b.modifiedAt - a.modifiedAt),
        empty: "还没有收藏。打开文档后点 ☆ 收藏。",
        recent: false,
      };
    }
    const dir = view.nav.dir;
    return {
      items: docs
        .filter((d) => (dir === null ? true : d.rel_path.startsWith(`${dir}/`)))
        .map(itemOf)
        .sort((a, b) => b.modifiedAt - a.modifiedAt),
      empty: "该目录下没有文档。",
      recent: false,
    };
  }, [docs, view, favorites]);

  const viewTitle =
    view.kind === "list"
      ? view.nav.kind === "all"
        ? "全部文档"
        : view.nav.kind === "recent"
          ? "最近"
          : view.nav.kind === "favorites"
            ? "收藏"
            : view.nav.title
      : view.kind === "search"
        ? `搜索：${view.q}`
        : "";

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => setView({ kind: "home" })}>
          📚 本地知识库
        </button>
        <div className="search">
          <input
            ref={searchRef}
            type="search"
            placeholder="搜索全部文档…（如：sqlite 中文检索）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runSearch(query);
            }}
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="hint">Ctrl K</kbd>
        </div>
        <div className="topbar-actions">
          {view.kind === "reader" && (
            <button className="text-btn" onClick={() => shareDoc(view.id)}>
              Share
            </button>
          )}
          <div className="more">
            <button className="text-btn" onClick={() => setShowMore((v) => !v)}>
              More
            </button>
            {showMore && (
              <div className="menu" onMouseLeave={() => setShowMore(false)}>
                <button onClick={() => { refetch(); setShowMore(false); }}>刷新文档列表</button>
                <button onClick={() => { window.location.href = "/docs"; }}>API 文档</button>
                <button onClick={() => { setShowMore(false); setView({ kind: "home" }); }}>首页</button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="content">
        <aside className="sidebar">
          {loadError && <div className="list-empty">加载失败：{loadError}</div>}
          {docs && (
            <Navigation
              docs={docs}
              favorites={favorites}
              active={view.kind === "list" ? view.nav : null}
              onSelect={(nav) => setView({ kind: "list", nav })}
              onOpenDoc={openDoc}
            />
          )}
        </aside>
        <main className="main" id="main-scroll">
          {view.kind === "home" && (
            <div className="home">
              <h2>欢迎</h2>
              <p className="dim">
                {docs ? `${docs.length} 篇文档已索引` : "加载中…"}。从左侧选择一个集合，
                或直接搜索。阅读器中点击相对链接 / WikiLink 可直接跳转。
              </p>
              {docs && (
                <>
                  <h3>最近更新</h3>
                  <DocListView
                    items={docs.map(itemOf).sort((a, b) => b.modifiedAt - a.modifiedAt).slice(0, 8)}
                    onOpen={openDoc}
                  />
                </>
              )}
            </div>
          )}
          {view.kind === "list" && (
            <div className="page-wrap">
              <h2 className="page-title">{viewTitle}</h2>
              <DocListView
                items={listContent.items}
                empty={listContent.empty}
                recent={listContent.recent}
                onOpen={openDoc}
              />
            </div>
          )}
          {view.kind === "search" && (
            <div className="page-wrap">
              <SearchResults results={view.results} onOpen={openDoc} />
            </div>
          )}
          {view.kind === "reader" && (
            <Reader
              key={view.id}
              docId={view.id}
              docs={docs}
              favorite={favorites.has(view.id)}
              onToggleFavorite={toggleFavorite}
              onShare={shareDoc}
              onClose={() => setView({ kind: "home" })}
              onOpen={openDoc}
            />
          )}
        </main>
      </div>
    </div>
  );
}