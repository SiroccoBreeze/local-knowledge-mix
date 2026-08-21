/** Feed 视图：把文档列表渲染为论坛式卡片流。 */

import { type DocMeta } from "../api";
import { fmtDate } from "../docview";
import { PostCard, type FeedItem } from "./PostCard";

export interface FeedDescriptor {
  title: string;
  items: FeedItem[];
  empty?: string;
}

export function docsToFeed(
  docs: DocMeta[],
  favorites: Set<number>,
  opts?: { sort?: "updated" | "title"; highlightFor?: (doc: DocMeta) => string | undefined }
): FeedItem[] {
  const sorted = [...docs].sort((a, b) =>
    opts?.sort === "title"
      ? (a.title || "").localeCompare(b.title || "", "zh-Hans-CN")
      : b.mtime_ns - a.mtime_ns
  );
  return sorted.map((d) => ({
    id: d.id,
    title: d.title || d.rel_path,
    relPath: d.rel_path,
    collection: d.rel_path.includes("/") ? d.rel_path.split("/")[0] : "根目录",
    updatedAt: fmtDate(d.mtime_ns),
    highlight: opts?.highlightFor?.(d),
    pinned: favorites.has(d.id),
  }));
}

interface Props {
  title?: string;
  items: FeedItem[];
  empty?: string;
  onOpen: (id: number, relPath: string) => void;
  onCopy: (id: number) => void;
  onTogglePin: (id: number) => void;
}

export function DocFeed({ title, items, empty, onOpen, onCopy, onTogglePin }: Props) {
  if (items.length === 0) {
    return <p className="py-20 text-center text-sm text-zinc-400 dark:text-zinc-500">{empty ?? "这里还没有文档。"}</p>;
  }
  return (
    <div>
      {title && (
        <h2 className="mb-4 text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">{title}</h2>
      )}
      <div className="grid gap-2">
        {items.map((it) => (
          <PostCard
            key={it.id}
            item={it}
            onOpen={() => onOpen(it.id, it.relPath)}
            onCopy={() => onCopy(it.id)}
            onTogglePin={() => onTogglePin(it.id)}
          />
        ))}
      </div>
    </div>
  );
}