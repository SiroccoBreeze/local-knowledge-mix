import { useMemo, useState } from "react";

import { type DocMeta } from "../api";

export type NavTarget =
  | { kind: "all" }
  | { kind: "recent" }
  | { kind: "favorites" }
  | { kind: "dir"; dir: string | null; title: string };

interface Props {
  docs: DocMeta[];
  favorites: Set<number>;
  active: NavTarget | null;
  onSelect: (t: NavTarget) => void;
  onOpenDoc: (id: number, relPath: string) => void;
}

interface DirNode {
  name: string;
  path: string;
  dirs: Map<string, DirNode>;
  docs: DocMeta[];
}

function buildHierarchy(docs: DocMeta[]): DirNode {
  const root: DirNode = { name: "", path: "", dirs: new Map(), docs: [] };
  for (const doc of docs) {
    const segs = doc.rel_path.split("/");
    segs.pop();
    let node = root;
    let path = "";
    for (const seg of segs) {
      path = path ? `${path}/${seg}` : seg;
      let child = node.dirs.get(seg);
      if (!child) {
        child = { name: seg, path, dirs: new Map(), docs: [] };
        node.dirs.set(seg, child);
      }
      node = child;
    }
    node.docs.push(doc);
  }
  return root;
}

export function Navigation({ docs, favorites, active, onSelect, onOpenDoc }: Props) {
  const root = useMemo(() => buildHierarchy(docs), [docs]);
  const favoritesCount = useMemo(
    () => docs.filter((d) => favorites.has(d.id)).length,
    [docs, favorites]
  );
  const [open, setOpen] = useState<Set<string>>(new Set());

  const toggle = (path: string) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const render = (node: DirNode, depth: number) => {
    const entries = [...node.dirs.values()].sort((a, b) =>
      a.name.localeCompare(b.name, "zh-Hans-CN")
    );
    return (
      <ul className="nav-tree">
        {entries.map((dir) => {
          const isOpen = open.has(dir.path);
          const isActiveDir =
            active?.kind === "dir" && "dir" in active && active.dir === dir.path;
          return (
            <li key={dir.path}>
              <button
                className={`nav-row nav-dir ${isActiveDir ? "active" : ""}`}
                onClick={() => {
                  toggle(dir.path);
                  onSelect({ kind: "dir", dir: dir.path, title: dir.name });
                }}
              >
                <span className={`caret ${isOpen ? "open" : ""}`}>▸</span>
                {dir.name}
                <span className="count">{dir.docs.length}</span>
              </button>
              {isOpen && render(dir, depth + 1)}
            </li>
          );
        })}
        {node.docs
          .sort((a, b) => a.title.localeCompare(b.title, "zh-Hans-CN"))
          .map((doc) => (
            <li key={doc.id}>
              <button
                className="nav-row nav-doc"
                title={doc.rel_path}
                onClick={() => onOpenDoc(doc.id, doc.rel_path)}
              >
                {doc.title || doc.rel_path}
              </button>
            </li>
          ))}
      </ul>
    );
  };

  return (
    <nav className="nav">
      <button
        className={`nav-row ${active?.kind === "all" ? "active" : ""}`}
        onClick={() => onSelect({ kind: "all" })}
      >
        🗂 全部文档 <span className="count">{docs.length}</span>
      </button>
      <button
        className={`nav-row ${active?.kind === "recent" ? "active" : ""}`}
        onClick={() => onSelect({ kind: "recent" })}
      >
        🕘 最近
      </button>
      <button
        className={`nav-row ${active?.kind === "favorites" ? "active" : ""}`}
        onClick={() => onSelect({ kind: "favorites" })}
      >
        ★ 收藏
        {favoritesCount > 0 && <span className="count">{favoritesCount}</span>}
      </button>

      <div className="nav-group-label">Collections</div>
      {render(root, 0)}
    </nav>
  );
}