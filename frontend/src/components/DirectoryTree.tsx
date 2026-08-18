import { useMemo, useState } from "react";

import { type DocMeta } from "../api";

interface Props {
  docs: DocMeta[];
  selected: string | null;
  onSelectDir: (dir: string | null) => void;
  onOpenDoc: (id: number, relPath: string) => void;
}

interface DirNode {
  name: string;
  path: string; // 空串 = 根
  dirs: Map<string, DirNode>;
  docs: DocMeta[];
}

function buildTree(docs: DocMeta[]): DirNode {
  const root: DirNode = { name: "", path: "", dirs: new Map(), docs: [] };
  for (const doc of docs) {
    const segments = doc.rel_path.split("/");
    segments.pop(); // 文件名；节点按目录构建
    let node = root;
    let path = "";
    for (const seg of segments) {
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

export function DirectoryTree({ docs, selected, onSelectDir, onOpenDoc }: Props) {
  const root = useMemo(() => buildTree(docs), [docs]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const render = (node: DirNode, depth: number): React.ReactNode => {
    const entries = [...node.dirs.values()].sort((a, b) =>
      a.name.localeCompare(b.name, "zh-Hans-CN")
    );
    return (
      <ul>
        {entries.map((dir) => {
          const isOpen = expanded.has(dir.path);
          const isSelected = selected === dir.path;
          return (
            <li key={dir.path}>
              <span
                className={`tree-dir ${isSelected ? "selected" : ""}`}
                onClick={() => {
                  toggle(dir.path);
                  onSelectDir(dir.path);
                }}
              >
                <span className="caret">{isOpen ? "▾" : "▸"}</span>
                {dir.name}
              </span>
              {isOpen && render(dir, depth + 1)}
            </li>
          );
        })}
        {node.docs
          .sort((a, b) => a.rel_path.localeCompare(b.rel_path, "zh-Hans-CN"))
          .map((doc) => (
            <li key={doc.id}>
              <span
                className="tree-doc"
                title={doc.rel_path}
                onClick={() => onOpenDoc(doc.id, doc.rel_path)}
              >
                {doc.title || doc.rel_path}
              </span>
            </li>
          ))}
      </ul>
    );
  };

  return (
    <div className="tree" onDoubleClick={() => setExpanded(new Set())}>
      <div
        className={`tree-dir ${selected === null ? "selected" : ""}`}
        onClick={() => onSelectDir(null)}
      >
        📁 全部文档（{docs.length}）
      </div>
      {render(root, 0)}
    </div>
  );
}