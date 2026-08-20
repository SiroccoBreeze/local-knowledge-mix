import { useEffect, useMemo, useRef, useState } from "react";

import { listAllDocuments, type DocMeta } from "./api";
import { CommandPalette } from "./components/CommandPalette";
import { Home } from "./components/Home";
import { ListView, itemOf } from "./components/ListView";
import { Navigation, type NavTarget } from "./components/Navigation";
import { Reader } from "./components/Reader";
import { ShareView } from "./components/ShareView";

type View =
  | { kind: "home" }
  | { kind: "list"; nav: NavTarget }
  | { kind: "reader"; id: number; relPath: string };

const FAV_KEY = "lk:favorites";
const RECENT_KEY = "lk:recent-visits";

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
  const [docs, setDocs] = useState<DocMeta[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<View>({ kind: "home" });
  const [favorites, setFavorites] = useState<Set<number>>(() => new Set(loadJSON<number[]>(FAV_KEY, [])));
  const [visits, setVisits] = useState<{ id: number; relPath: string; ts: number }[]>(() =>
    loadJSON(RECENT_KEY, [])
  );
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shareId, setShareId] = useState<number | null>(() => shareIdFrom(window.location.pathname));
  const shareIdRef = useRef(shareId);

  // ------- 数据 -------
  const refetch = () => {
    listAllDocuments()
      .then(setDocs)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(() => {
    refetch();
  }, []);

  // ------- 路由：/share/{id}（popstate 前进/后退） -------
  useEffect(() => {
    shareIdRef.current = shareId;
  }, [shareId]);

  useEffect(() => {
    const onPop = () => {
      const sid = shareIdFrom(window.location.pathname);
      if (sid === null && shareIdRef.current !== null) {
        setView({ kind: "home" });
      }
      setShareId(sid);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // ------- 快捷键：⌘K 打开搜索 / Esc 关闭 -------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (e.key === "Escape" && paletteOpen) {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen]);

  // ------- 打开 / 收藏 / 访问记录 -------
  const openDoc = (id: number, relPath: string) => {
    setView({ kind: "reader", id, relPath });
    setVisits((prev) => {
      const next = [{ id, relPath, ts: Date.now() }, ...prev.filter((v) => v.id !== id)].slice(0, 12);
      try {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      } catch {
        /* 降级 */
      }
      return next;
    });
    document.getElementById("main-scroll")?.scrollTo({ top: 0 });
  };

  const toggleFavorite = (id: number) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
      } catch {
        /* 降级 */
      }
      return next;
    });
  };

  // ---------- 派生数据（所有 hooks 在早退 return 之前） ----------
  const recentDocs = useMemo(
    () => (docs ? [...docs].sort((a, b) => b.mtime_ns - a.mtime_ns).slice(0, 5) : []),
    [docs]
  );

  const listContent = useMemo(() => {
    if (!docs) return { items: [] as ReturnType<typeof itemOf>[], title: "" };
    const sorted = [...docs].sort((a, b) => b.mtime_ns - a.mtime_ns);
    if (view.kind !== "list") return { items: [], title: "" };
    if (view.nav.kind === "all") return { items: sorted.map(itemOf), title: "全部" };
    if (view.nav.kind === "recent") return { items: sorted.slice(0, 30).map(itemOf), title: "最近" };
    if (view.nav.kind === "favorites") {
      return { items: sorted.filter((d) => favorites.has(d.id)).map(itemOf), title: "收藏" };
    }
    const dir = view.nav.dir;
    return {
      items: docs
        .filter((d) => (dir === null ? true : d.rel_path.startsWith(`${dir}/`)))
        .sort((a, b) => b.mtime_ns - a.mtime_ns)
        .map(itemOf),
      title: view.nav.title || "全部",
    };
  }, [docs, view, favorites]);

  if (shareId !== null) {
    return (
      <div className="app share-mode">
        <div className="share-page">
          <ShareView docId={shareId} />
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <Navigation
          docs={docs ?? []}
          favorites={favorites}
          active={view.kind === "list" ? view.nav : null}
          onSelect={(nav) => setView({ kind: "list", nav })}
          onOpenDoc={openDoc}
          onOpenSearch={() => setPaletteOpen(true)}
        />
      </aside>

      <main className="main" id="main-scroll">
        {view.kind === "home" && (
          <Home
            docs={docs}
            recentVisits={visits}
            recentDocs={recentDocs}
            onOpenDoc={openDoc}
            onOpenSearch={() => setPaletteOpen(true)}
          />
        )}
        {view.kind === "list" && (
          <ListView
            title={listContent.title}
            items={listContent.items}
            onOpen={openDoc}
            empty={loadError ? `加载失败：${loadError}` : "这里还没有文档。"}
          />
        )}
        {view.kind === "reader" && (
          <Reader
            key={view.id}
            docId={view.id}
            favorite={favorites.has(view.id)}
            onToggleFavorite={toggleFavorite}
            onBack={() => setView({ kind: "home" })}
            onOpen={openDoc}
          />
        )}
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onOpenDoc={openDoc} />
    </div>
  );
}