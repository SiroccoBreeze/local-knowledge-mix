/** /share/{id} —— 只读分享页（新视觉：顶栏 + 正文流）。 */

import { useEffect, useState } from "react";
import { BookOpen } from "lucide-react";

import { ReaderContent } from "./ReaderContent";

interface Props {
  docId: number;
}

export function ShareView({ docId }: Props) {
  const [cur, setCur] = useState(docId);
  useEffect(() => setCur(docId), [docId]);

  const navigate = (id: number) => {
    setCur(id);
    try {
      window.history.pushState({}, "", `/share/${id}`);
    } catch {
      /* 本地文件/旧浏览器降级 */
    }
  };

  return (
    <div className="flex h-screen flex-col bg-zinc-50 dark:bg-zinc-950">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-200/70 bg-white/80 px-4 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/80">
        <span className="flex items-center gap-2 text-[13px] font-semibold text-zinc-900 dark:text-zinc-50">
          <BookOpen className="h-4 w-4 text-zinc-500 dark:text-zinc-400" />
          知识库 · 只读分享
        </span>
        <a href="/" className="text-[13px] text-zinc-500 transition-colors hover:text-zinc-900 dark:hover:text-zinc-100">
          回到知识库 →
        </a>
      </header>
      <div className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto">
        <ReaderContent
          docId={cur}
          favorite={false}
          onToggleFavorite={() => undefined}
          onOpen={(id) => navigate(id)}
          compact
        />
      </div>
    </div>
  );
}