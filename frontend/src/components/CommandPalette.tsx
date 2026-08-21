/** ⌘K 命令面板 —— 产品核心搜索入口（Linear 风）。 */

import { useEffect, useRef, useState } from "react";
import { Command, Search } from "lucide-react";

import { fmtDate } from "../docview";
import { search as apiSearch } from "../api";

export interface HitY {
  id: number;
  title: string;
  relPath: string;
  collection: string;
  updatedAtNs: number;
  score?: number;
  matched?: string[];
  highlight?: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onOpenDoc: (id: number, relPath: string) => void;
}

export function CommandPalette({ open, onClose, onOpenDoc }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<HitY[]>([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setHits([]);
    setActive(0);
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open || !q.trim()) {
      setHits([]);
      return;
    }
    const timer = setTimeout(() => {
      searchQuery(q.trim(), 12).then((r) => {
        setHits(r);
        setActive(0);
      });
    }, 180);
    return () => clearTimeout(timer);
  }, [q, open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(i + 1, hits.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const hit = hits[active];
        if (hit) {
          onOpenDoc(hit.id, hit.relPath);
          onClose();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, hits, active, onClose, onOpenDoc]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-start justify-center px-4 pt-[14vh]">
      <div className="fade-in absolute inset-0 bg-zinc-950/45 backdrop-blur-[2px]" onClick={onClose} />
      <div className="fade-in relative w-full max-w-[600px] overflow-hidden rounded-2xl border border-zinc-200/80 bg-white shadow-2xl dark:border-zinc-700 dark:bg-zinc-900">
        <div className="flex items-center gap-3 border-b border-zinc-100 px-4 dark:border-zinc-800">
          <Search className="h-[18px] w-[18px] text-zinc-400" />
          <input
            ref={inputRef}
            className="h-12 flex-1 bg-transparent text-[15px] text-zinc-900 placeholder:text-zinc-400 focus:outline-none dark:text-zinc-100"
            placeholder="搜索全部文档…（如：sqlite 中文检索）"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="flex items-center gap-0.5 rounded border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-500">
            <Command className="h-3 w-3" />
            K
          </kbd>
        </div>
        <div className="max-h-[46vh] overflow-y-auto p-1.5">
          {q.trim() === "" ? (
            <p className="px-4 py-6 text-center text-sm text-zinc-400">
              输入关键词开始搜索 · ↑↓ 选择 · Enter 打开 · Esc 关闭
            </p>
          ) : hits.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-zinc-400">没有匹配「{q.trim()}」的文档</p>
          ) : (
            hits.map((hit, i) => (
              <button
                key={hit.id}
                className={`block w-full rounded-lg px-3 py-2.5 text-left transition-colors ${
                  i === active ? "bg-zinc-100 dark:bg-zinc-800" : ""
                }`}
                onMouseEnter={() => setActive(i)}
                onClick={() => {
                  onOpenDoc(hit.id, hit.relPath);
                  onClose();
                }}
              >
                <span className="block text-[14.5px] font-semibold text-zinc-800 dark:text-zinc-100">{hit.title}</span>
                <span className="block text-[12px] text-zinc-400 dark:text-zinc-500">
                  {hit.collection} · {fmtDate(hit.updatedAtNs)}
                </span>
                {hit.highlight && (
                  <span
                    className="mt-0.5 block w-full truncate text-[12.5px] leading-relaxed text-zinc-500 dark:text-zinc-400"
                    dangerouslySetInnerHTML={{ __html: hit.highlight }}
                  />
                )}
                <span className="mt-1 flex flex-wrap items-center gap-1.5">
                  {hit.score !== undefined && (
                    <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-600 dark:text-amber-400">
                      相关度 {hit.score.toFixed(2)}
                    </span>
                  )}
                  {hit.matched && hit.matched.length > 0 && (
                    <span className="inline-flex flex-wrap gap-1">
                      {hit.matched.slice(0, 6).map((t) => (
                        <i key={t} className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] not-italic text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                          {t}
                        </i>
                      ))}
                    </span>
                  )}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function searchQuery(q: string, limit: number): Promise<HitY[]> {
  return apiSearch(q, limit).then((r) =>
    r.hits.map((h) => ({
      id: h.doc.id,
      title: h.doc.title || h.doc.rel_path,
      relPath: h.doc.rel_path,
      collection: h.doc.rel_path.split("/")[0] ?? "根目录",
      updatedAtNs: h.doc.mtime_ns,
      score: h.score,
      highlight: h.snippets[0]?.text,
    }))
  );
}

