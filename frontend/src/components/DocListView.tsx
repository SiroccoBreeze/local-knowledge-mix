import { type DocMeta } from "../api";
import { fmtDate } from "../docview";

export interface ListItem {
  id: number;
  title: string;
  relPath: string;
  collection: string;
  modifiedAt: number;
  tags: string[];
}

export function itemOf(d: DocMeta): ListItem {
  const tagRaw = d.frontmatter?.tags;
  const tags = Array.isArray(tagRaw) ? tagRaw.map(String) : typeof tagRaw === "string" ? [tagRaw] : [];
  return {
    id: d.id,
    title: d.title || d.rel_path,
    relPath: d.rel_path,
    collection: d.rel_path.includes("/") ? d.rel_path.split("/")[0] : "根目录",
    modifiedAt: d.mtime_ns,
    tags,
  };
}

interface Props {
  items: ListItem[];
  empty?: string;
  onOpen: (id: number, relPath: string) => void;
  recent?: boolean;
}

export function DocListView({ items, empty, onOpen, recent }: Props) {
  if (items.length === 0) {
    return <div className="list-empty">{empty ?? "这里还没有文档。"}</div>;
  }
  return (
    <div className="doc-list">
      {items.map((it) => (
        <button key={it.id} className="doc-row" onClick={() => onOpen(it.id, it.relPath)}>
          <span className="doc-title">
            {it.title}
            {recent && it.tags.length > 0 && (
              <span className="doc-tags">{it.tags.slice(0, 3).map((t) => <i key={t}>{t}</i>)}</span>
            )}
          </span>
          <span className="doc-meta">
            <span className="doc-collection">{it.collection}</span>
            <span className="separator">·</span>
            <span className="doc-time">{fmtDate(it.modifiedAt)}</span>
          </span>
        </button>
      ))}
    </div>
  );
}