/** 文档行（首页/列表/收藏/最近共用）。 */

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

export function DocRow({
  item,
  onOpen,
}: {
  item: ListItem;
  onOpen: (id: number, relPath: string) => void;
}) {
  return (
    <button className="doc-row" onClick={() => onOpen(item.id, item.relPath)}>
      <span className="doc-title">{item.title}</span>
      <span className="doc-meta">
        <span className="doc-collection">{item.collection}</span>
        {item.tags.length > 0 && (
          <span className="doc-tags-inline">
            {item.tags.slice(0, 2).map((t) => (
              <span key={t} className="meta-tag">
                #{t}
              </span>
            ))}
          </span>
        )}
        <span className="doc-time">{fmtDate(item.modifiedAt)}</span>
      </span>
    </button>
  );
}