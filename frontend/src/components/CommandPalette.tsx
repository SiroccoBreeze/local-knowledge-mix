/** ⌘K 命令面板 —— 产品核心搜索入口。 */

import { useEffect, useRef, useState } from "react";

import { type Hit, search } from "../api";
import { fmtDate } from "../docview";

interface Props {
  open: boolean;
  onClose: () => void;
  onOpenDoc: (id: number, relPath: string) => void;
}

export function CommandPalette({ open, onClose, onOpenDoc }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setHits([]);
    setActive(0);
    inputRef.current?.focus();
  }, [open]);

  // 输入防抖搜索
  useEffect(() => {
    if (!open || !q.trim()) {
      setHits([]);
      return;
    }
    const timer = setTimeout(() => {
      search(q.trim(), 12).then((r) => {
        setHits(r.hits);
        setActive(0);
      });
    }, 180);
    return () => clearTimeout(timer);
  }, [q, open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(i + 1, hits.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const hit = hits[active];
        if (hit) {
          onOpenDoc(hit.doc.id, hit.doc.rel_path);
          onClose();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, hits, active, onClose, onOpenDoc]);

  if (!open) return null;

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette-input"
          placeholder="搜索全部文档…（如：sqlite 中文检索）"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <div className="palette-results">
          {q.trim() === "" ? (
            <div className="palette-hint">输入关键词开始搜索 · ↑↓ 选择 · Enter 打开 · Esc 关闭</div>
          ) : hits.length === 0 ? (
            <div className="palette-hint">没有匹配「{q.trim()}」的文档</div>
          ) : (
            hits.map((hit, i) => (
              <button
                key={hit.doc.id}
                className={`palette-row ${i === active ? "active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => {
                  onOpenDoc(hit.doc.id, hit.doc.rel_path);
                  onClose();
                }}
              >
                <span className="palette-title">{hit.doc.title || hit.doc.rel_path}</span>
                <span className="palette-meta">
                  {hit.doc.rel_path.split("/")[0]} · {fmtDate(hit.doc.mtime_ns)}
                </span>
                {hit.snippets[0] && (
                  <span
                    className="palette-snippet"
                    dangerouslySetInnerHTML={{ __html: hit.snippets[0].text }}
                  />
                )}
                {hit.matched_terms.length > 0 && (
                  <span className="palette-stat">
                    <span className="palette-score">相关度 {hit.score.toFixed(2)}</span>
                    <span className="palette-terms">
                      {hit.matched_terms.slice(0, 5).map((t) => (
                        <i key={t} className="palette-term">
                          {t}
                        </i>
                      ))}
                    </span>
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}