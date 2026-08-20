/** 左栏（知识库浏览入口）：导航 + Collections，移动端抽屉式。 */

import { Archive, BookOpen, Clock, Star } from "lucide-react";

import type { FeedKind } from "./FilterPills";

interface Props {
  open: boolean;
  onClose: () => void;
  docsCount: number;
  favoritesCount: number;
  active: FeedKind | null;
  onSelect: (kind: FeedKind) => void;
  children?: React.ReactNode;
}

export function Sidebar({ open, onClose, docsCount, favoritesCount, active, onSelect, children }: Props) {
  const row = (flag: boolean) =>
    [
      "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] transition-colors",
      flag
        ? "bg-zinc-200/60 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50"
        : "text-zinc-600 hover:bg-zinc-200/50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100",
    ].join(" ");

  return (
    <>
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-zinc-200/70 bg-white transition-transform duration-200 dark:border-zinc-800 dark:bg-zinc-900 ${
          open ? "translate-x-0" : "-translate-x-full"
        } lg:static lg:z-0 lg:translate-x-0`}
      >
        <div className="flex items-center gap-2.5 px-4 pt-5 pb-3 text-[15px] font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
          <Archive className="h-4.5 w-4.5 h-[18px] w-[18px] text-zinc-500 dark:text-zinc-400" />
          知识库
        </div>

        <div className="px-2.5">
          <button className={row(active?.kind === "all")} onClick={() => onSelect({ kind: "all" })}>
            <Archive className="h-4 w-4" /> 全部文档
            <span className="ml-auto text-xs text-zinc-400 dark:text-zinc-500">{docsCount}</span>
          </button>
          <button className={row(active?.kind === "recent")} onClick={() => onSelect({ kind: "recent" })}>
            <Clock className="h-4 w-4" /> 最近
          </button>
          <button className={row(active?.kind === "favorites")} onClick={() => onSelect({ kind: "favorites" })}>
            <Star className="h-4 w-4" /> 收藏
            {favoritesCount > 0 && (
              <span className="ml-auto text-xs text-zinc-400 dark:text-zinc-500">{favoritesCount}</span>
            )}
          </button>

          <div className="mt-5 mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            Collections
          </div>
          {children}
        </div>

        <div className="mt-auto border-t border-zinc-100 px-3 py-3 text-xs text-zinc-400 dark:border-zinc-800 dark:text-zinc-500">
          <BookOpen className="mr-1 inline h-3.5 w-3.5" />
          本地知识库 · api v1
        </div>
      </aside>

      {open && <div className="fade-in fixed inset-0 z-30 bg-zinc-950/40 lg:hidden" onClick={onClose} />}
    </>
  );
}