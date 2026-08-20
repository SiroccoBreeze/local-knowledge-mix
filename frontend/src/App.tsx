import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getDocContent,
  listAllDocuments,
  type DocMeta,
} from "./api";
import { CommandPalette } from "./components/CommandPalette";
import { DocFeed, docsToFeed } from "./components/DocFeed";
import { FilterPills, type FeedKind } from "./components/FilterPills";
import { Navbar } from "./components/Navbar";
import { ReaderContent } from "./components/ReaderContent";
import { ShareView } from "./components/ShareView";
import { Sidebar } from "./components/Sidebar";
import { ToastProvider, useToast } from "./components/Toast";

const FAV_KEY = "lk:favorites";
const RECENT_KEY = "lk:recent-visits";
const THEME_KEY = "lk:theme";

function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function shareIdFrom(path: string): number | null {
  const m = /^\/share\/(\d+)\/?$/.exec(path);
  return m ? Number(m[1]) : null;
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

function Shell() {
  const toast = useToast();
  const [docs, setDocs] = useState<DocMeta[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [kind, setKind] = useState<FeedKind>({ kind: "all" });
  const [sort, setSort] = useState<"updated" | "title">("updated");
  const [favorites, setFavorites] = useState<Set<number>>(() => new Set(loadJSON<number[]>(FAV_KEY, [])));
  const [visits, setVisits] = useState<{ id: number; relPath: string; ts: number }[]>(() => loadJSON(RECENT_KEY, []));
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activeDoc, setActiveDoc] = useState<{ id: number; relPath: string } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => (localStorage.getItem(THEME_KEY) as "dark" | "light") ?? "light");
  const [shareId, setShareId] = useState<number | null>(() => shareIdFrom(window.location.pathname));
  const shareIdRef = useRef(shareId);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* 降级 */
    }
  }, [theme]);

  useEffect(() => {
    listAllDocuments()
      .then(setDocs)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    shareIdRef.current = shareId;
  }, [shareId]);

  useEffect(() => {
    const onPop = () => {
      const sid = shareIdFrom(window.location.pathname);
      if (sid === null && shareIdRef.current !== null) {
        setActiveDoc(null);
      }
      setShareId(sid);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (e.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openDoc = (id: number, relPath: string) => {
    setActiveDoc({ id, relPath });
    setVisits((prev) => {
      const next = [{ id, relPath, ts: Date.now() }, ...prev.filter((v) => v.id !== id)].slice(0, 12);
      try {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      } catch {
        /* 降级 */
      }
      return next;
    });
  };

  const copyBody = useCallback(
    (id: number) => {
      getDocContent(id)
        .then((text) =>
          navigator.clipboard
            ?.writeText(text)
            .then(() => toast("✓ 已复制原文"))
            .catch(() => toast("复制失败"))
        )
        .catch(() => toast("读取原文失败"));
    },
    [toast]
  );

  const togglePin = (id: number) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        toast("已取消固定");
      } else {
        next.add(id);
        toast("已固定 ★");
      }
      try {
        localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
      } catch {
        /* 降级 */
      }
      return next;
    });
  };

  const feedTitle =
    kind.kind === "all" ? "全部文档" : kind.kind === "recent" ? "最近访问" : kind.kind === "favorites" ? "收藏" : kind.title;


  if (shareId !== null) {
    return <ShareView docId={shareId} />;
  }

  const items = useMemo(() => {
    if (!docs) return [] as ReturnType<typeof docsToFeed>;
    if (kind.kind === "recent") {
      const recents = docs.filter((d) => visits.some((v) => v.id === d.id));
      return docsToFeed(recents, favorites, { sort });
    }
    if (kind.kind === "favorites") return docsToFeed(docs, favorites, { sort }).filter((it) => it.pinned);
    if (kind.kind === "all") return docsToFeed(docs, favorites, { sort });
    const dir = kind.dir;
    const filtered = docs.filter((d) => (dir === null ? true : d.rel_path.startsWith(`${dir}/`)));
    return docsToFeed(filtered, favorites, { sort });
  }, [docs, kind, sort, favorites, visits]);

  const collections = useMemo(() => {
    if (!docs) return [] as { dir: string; count: number }[];
    const m = new Map<string, number>();
    for (const d of docs) {
      const dir = d.rel_path.includes("/") ? d.rel_path.split("/")[0] : null;
      if (dir) m.set(dir, (m.get(dir) ?? 0) + 1);
    }
    return [...m.entries()]
      .map(([dir, count]) => ({ dir, count }))
      .sort((a, b) => a.dir.localeCompare(b.dir, "zh-Hans-CN"));
  }, [docs]);

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        docsCount={docs?.length ?? 0}
        favoritesCount={favorites.size}
        active={kind}
        onSelect={(k) => {
          setKind(k);
          setSidebarOpen(false);
        }}
      >
        <div className="px-2.5">
          {collections.map((c) => (
            <button
              key={c.dir}
              onClick={() => setKind({ kind: "dir", dir: c.dir, title: c.dir })}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13.5px] transition-colors ${
                kind.kind === "dir" && kind.dir === c.dir
                  ? "bg-zinc-200/60 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50"
                  : "text-zinc-600 hover:bg-zinc-200/50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100"
              }`}
            >
              {c.dir}
              <span className="ml-auto text-xs text-zinc-400 dark:text-zinc-500">{c.count}</span>
            </button>
          ))}
        </div>
      </Sidebar>

      <div className="flex min-w-0 flex-1 flex-col">
        <Navbar
          theme={theme}
          onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          onOpenSearch={() => setPaletteOpen(true)}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
        />
        <FilterPills
          docs={docs ?? []}
          favorites={favorites}
          active={kind}
          sort={sort}
          onSelect={setKind}
          onSort={setSort}
        />

        {!activeDoc && (
        <main className="mx-auto w-full max-w-[960px] flex-1 overflow-y-auto px-4 py-5">
          {kind.kind === "all" && (
            <div className="mb-5 flex items-baseline justify-between">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                本地知识库 · <span className="font-semibold text-zinc-900 dark:text-zinc-50">{docs?.length ?? "…"}</span> 篇文档
              </p>
              {visits.length > 0 && (
                <button
                  onClick={() => setKind({ kind: "recent" })}
                  className="text-[13px] text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200"
                >
                  最近访问 →
                </button>
              )}
            </div>
          )}
          {loadError ? (
            <p className="py-20 text-center text-sm text-rose-500">{loadError}</p>
          ) : (
            <DocFeed
              title={kind.kind === "all" ? undefined : feedTitle}
              items={items}
              empty={kind.kind === "favorites" ? "还没有收藏。打开文档后点 ☆ 固定。" : "这里还没有文档。"}
              onOpen={openDoc}
              onCopy={copyBody}
              onTogglePin={togglePin}
            />
          )}
        </main>
        )}

      {activeDoc && (
        <div className="flex min-w-0 flex-1 overflow-hidden border-t border-zinc-200/60 dark:border-zinc-800">
          <aside className="hidden w-80 shrink-0 overflow-y-auto border-r border-zinc-200/70 bg-white px-2 py-3 dark:border-zinc-800 dark:bg-zinc-900 md:block">
            <DocFeed
              title={kind.kind === "all" ? undefined : feedTitle}
              items={items}
              empty="没有文档。"
              onOpen={openDoc}
              onCopy={copyBody}
              onTogglePin={togglePin}
            />
          </aside>
          <section key={activeDoc.id} className="min-w-0 flex-1 overflow-y-auto">
            <ReaderContent
              docId={activeDoc.id}
              favorite={favorites.has(activeDoc.id)}
              onToggleFavorite={togglePin}
              onOpen={openDoc}
              onBack={() => setActiveDoc(null)}
            />
          </section>
        </div>
      )}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onOpenDoc={openDoc} />
      </div>
    </div>
  );
}