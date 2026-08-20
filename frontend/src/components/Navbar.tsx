/** 顶部系统栏：品牌 / 居中搜索 / 主题与设置。 */

import { BookOpen, Command, Menu, Moon, Search, Sun } from "lucide-react";

interface Props {
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onOpenSearch: () => void;
  onToggleSidebar: () => void;
}

export function Navbar({ theme, onToggleTheme, onOpenSearch, onToggleSidebar }: Props) {
  return (
    <header className="sticky top-0 z-40 border-b border-zinc-200/70 bg-zinc-50/80 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/80">
      <div className="mx-auto flex h-14 max-w-[960px] items-center gap-2 px-4">
        <button
          onClick={onToggleSidebar}
          className="rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-200/70 hover:text-zinc-800 lg:hidden dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2 font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          <BookOpen className="h-5 w-5 text-zinc-500 dark:text-zinc-400" />
          <span className="hidden sm:inline">知识库</span>
        </div>

        <button
          onClick={onOpenSearch}
          className="group mx-auto flex h-9 w-full max-w-md items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-500 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-all duration-200 hover:border-zinc-300 hover:shadow-md dark:border-zinc-700/80 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:border-zinc-600"
        >
          <Search className="h-4 w-4" />
          <span className="flex-1 text-left">搜索全部文档…</span>
          <kbd className="flex items-center gap-0.5 rounded border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-500">
            <Command className="h-3 w-3" />
            K
          </kbd>
        </button>

        <button
          onClick={onToggleTheme}
          title="切换主题"
          className="ml-auto rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-200/70 hover:text-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
        >
          {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </div>
    </header>
  );
}