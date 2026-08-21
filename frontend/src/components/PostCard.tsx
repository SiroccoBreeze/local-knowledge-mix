/** 论坛式内容卡片（Post Card）：分类 Tag / 得分 Badge / 时间 / 标题 / 高亮摘要 / 操作。 */

import { ArrowUpRight, Copy, Pin } from "lucide-react";

export interface FeedItem {
  id: number;
  title: string;
  relPath: string;
  collection: string;
  updatedAt: string;
  score?: number;
  highlight?: string; // HTML snippet（含 <mark>）
  pinned: boolean;
}

interface Props {
  item: FeedItem;
  onOpen: () => void;
  onCopy: () => void;
  onTogglePin: () => void;
}

export function PostCard({ item, onOpen, onCopy, onTogglePin }: Props) {
  return (
    <article
      onClick={onOpen}
      onKeyDown={(e) => {
        // 仅当卡片本体聚焦时响应 Enter / Space（内部复制/固定按钮不重复触发）
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={item.title}
      className="group cursor-pointer rounded-xl border border-transparent bg-white p-3 text-left outline-none transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-400 hover:border-slate-300 hover:shadow-md dark:bg-zinc-900 dark:hover:border-slate-600 dark:focus-visible:outline-zinc-500"
    >
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="rounded-full bg-zinc-100 px-2 py-px font-medium tracking-wide text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
          {item.collection}
        </span>
        {item.score !== undefined && (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 font-medium text-amber-600 dark:text-amber-400">
            相关度 {item.score.toFixed(2)}
          </span>
        )}
        <span className="ml-auto text-zinc-400 dark:text-zinc-500">{item.updatedAt}</span>
      </div>

      <h3 className="mt-1.5 break-words text-[15px] font-bold leading-snug tracking-tight text-zinc-900 group-hover:underline decoration-zinc-300 underline-offset-4 dark:text-zinc-100 dark:decoration-zinc-700">
        {item.title}
      </h3>

      {item.highlight && (
        <p
          className="mt-1 line-clamp-2 text-[13px] leading-snug text-zinc-600 dark:text-zinc-300"
          dangerouslySetInnerHTML={{ __html: item.highlight }}
        />
      )}

      <div className="mt-2 flex items-center gap-1 text-[11.5px] text-zinc-400 dark:text-zinc-500">
        <button
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          onClick={(e) => {
            e.stopPropagation();
            onCopy();
          }}
        >
          <Copy className="h-3.5 w-3.5" />
          复制原文
        </button>
        <button
          className={`inline-flex items-center gap-1 rounded-md px-2 py-1 transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800 ${
            item.pinned ? "text-amber-500" : "hover:text-zinc-700 dark:hover:text-zinc-200"
          }`}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin();
          }}
        >
          <Pin className={`h-3.5 w-3.5 ${item.pinned ? "fill-amber-400" : ""}`} />
          {item.pinned ? "取消固定" : "固定"}
        </button>
        <span className="ml-auto">
          <ArrowUpRight className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-70" />
        </span>
      </div>
    </article>
  );
}