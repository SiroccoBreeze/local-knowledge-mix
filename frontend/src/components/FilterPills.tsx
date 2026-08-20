/** 次级筛选栏：分类 / 视图 / 排序的平滑圆角标签组。 */

export type FeedKind =
  | { kind: "all" }
  | { kind: "recent" }
  | { kind: "favorites" }
  | { kind: "dir"; dir: string | null; title: string };

interface Props {
  docs: DocMetaLike[];
  favorites: Set<number>;
  active: FeedKind | null;
  sort: "updated" | "title";
  onSelect: (kind: FeedKind) => void;
  onSort: (sort: "updated" | "title") => void;
}

interface DocMetaLike {
  id: number;
  rel_path: string;
}

export function FilterPills({ docs, favorites, active, sort, onSelect, onSort }: Props) {
  const dirs = new Map<string, number>();
  for (const d of docs) {
    const dir = d.rel_path.includes("/") ? d.rel_path.split("/")[0] : null;
    if (dir) dirs.set(dir, (dirs.get(dir) ?? 0) + 1);
  }

  const pill = (activeFlag: boolean) =>
    [
      "rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-all duration-200",
      activeFlag
        ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900"
        : "text-zinc-500 hover:bg-zinc-200/60 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100",
    ].join(" ");

  return (
    <div className="sticky top-14 z-30 border-b border-zinc-200/60 bg-zinc-50/90 backdrop-blur dark:border-zinc-800/60 dark:bg-zinc-950/90">
      <div className="mx-auto flex max-w-[960px] items-center gap-2 overflow-x-auto px-4 py-2.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button className={pill(active?.kind === "all")} onClick={() => onSelect({ kind: "all" })}>
          全部文档 <span className="opacity-60">{docs.length}</span>
        </button>
        <button className={pill(active?.kind === "recent")} onClick={() => onSelect({ kind: "recent" })}>
          最近
        </button>
        <button className={pill(active?.kind === "favorites")} onClick={() => onSelect({ kind: "favorites" })}>
          收藏{" "}
          {favorites.size > 0 && <span className="opacity-60">{favorites.size}</span>}
        </button>
        {[...dirs.entries()]
          .sort((a, b) => a[0].localeCompare(b[0], "zh-Hans-CN"))
          .map(([dir, count]) => (
            <button
              key={dir}
              className={pill(active?.kind === "dir" && active.dir === dir)}
              onClick={() => onSelect({ kind: "dir", dir, title: dir })}
            >
              {dir} <span className="opacity-60">{count}</span>
            </button>
          ))}
        <span className="mx-1 h-5 w-px bg-zinc-300/70 dark:bg-zinc-700" />
        <button className={pill(sort === "updated")} onClick={() => onSort("updated")} title="按更新时间排序">
          最新
        </button>
        <button className={pill(sort === "title")} onClick={() => onSort("title")} title="按标题排序">
          标题
        </button>
      </div>
    </div>
  );
}