import { useEffect, useMemo, useRef, useState } from "react";
import { Marked, type RendererObject, type Token } from "marked";

import { dirOf, getDocContent, getNeighbors, rawUrl } from "../api";

interface Props {
  docId: number;
  relPath: string;
  onClose: () => void;
  onOpen: (id: number, relPath: string) => void;
}

interface LinkTarget {
  id: number;
  title: string;
  rel_path: string;
}

const WIKI_SCHEME = "lk-wiki:";
const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** 把 marked 行内 token 摊平成纯文本（用于标题 id 与链接文字）。 */
function tokenText(t: string | Token): string {
  if (typeof t === "string") return t;
  if (Array.isArray((t as { tokens?: Token[] }).tokens)) {
    return (t as { tokens: Token[] }).tokens.map(tokenText).join("");
  }
  return (t as { text?: string }).text ?? "";
}

function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\s_-]/gu, "")
    .replace(/\s+/g, "-");
}

/** [[目标]] / [[目标|别名]] → markdown 链接（代码围栏内不处理）。 */
export function preprocessWiki(md: string): string {
  const lines = md.split("\n");
  let inFence = false;
  const out: string[] = [];
  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) inFence = !inFence;
    if (!inFence) {
      out.push(
        line.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_m, target: string, alias?: string) => {
          const t = (target ?? "").trim();
          const show = (alias?.trim() || t).replace(/[[\]()]/g, "");
          return `[${show}](${WIKI_SCHEME}${encodeURIComponent(t)})`;
        })
      );
    } else {
      out.push(line);
    }
  }
  return out.join("\n");
}

/** 相对图片/链接路径 → 相对 raw/ 的路径（绝对路径或逃逸返回 null）。 */
function resolveRelPath(dir: string, href: string): string | null {
  if (href.startsWith("/") || /^[a-zA-Z]:/.test(href)) return null;
  const parts = dir ? dir.split("/") : [];
  for (const seg of decodeURIComponent(href).split("/")) {
    if (seg === "..") {
      if (parts.length) parts.pop();
      else return null;
    } else if (seg === "." || seg === "") {
      continue;
    } else {
      parts.push(seg);
    }
  }
  return parts.join("/");
}

interface DomProps {
  content: string;
  relPath: string;
  linkMap: Map<string, LinkTarget>;
}

/** 渲染 markdown → HTML（GitHub 风格；图片/相对链接走本地安全访问）。 */
export function renderMarkdown({ content, relPath, linkMap }: DomProps): string {
  const dir = dirOf(relPath);
  let idIndex = 0;
  const usedIds = new Set<string>();

  const uniqueId = (slug: string) => {
    const base = slug || `h${++idIndex}`;
    let id = base;
    let n = 2;
    while (usedIds.has(id)) id = `${base}-${n++}`;
    usedIds.add(id);
    return id;
  };

  const renderer: RendererObject = {
    heading({ tokens, depth }) {
      const text = esc(tokens.map(tokenText).join(""));
      const id = uniqueId(slugify(text));
      const size = depth <= 6 ? depth : 6;
      return `<h${size} id="${id}">${text}</h${size}>`;
    },
    link({ href, tokens }) {
      const text = esc(tokens.map(tokenText).join(""));
      const t = href ?? "";
      if (t.startsWith(WIKI_SCHEME)) {
        const target = decodeURIComponent(t.slice(WIKI_SCHEME.length));
        const nb = linkMap.get(target);
        if (nb) {
          return `<a href="#" data-open="${nb.id}" data-title="${esc(nb.title)}" data-path="${esc(
            nb.rel_path
          )}">${text}</a>`;
        }
        return `<a href="#" class="dangling" title="未解析的 WikiLink：${esc(target)}">${text}</a>`;
      }
      if (t.startsWith("http://") || t.startsWith("https://")) {
        return `<a href="${esc(t)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
      }
      if (t.startsWith("#")) {
        return `<a href="${esc(t)}">${text}</a>`;
      }
      // 相对 .md 链接：与 neighbors 的原始 target 精确匹配
      const nb = linkMap.get(t);
      if (nb) {
        return `<a href="#" data-open="${nb.id}" data-title="${esc(nb.title)}" data-path="${esc(
          nb.rel_path
        )}">${text}</a>`;
      }
      const hrefBase = t.split("#")[0];
      if (hrefBase) {
        const byT = linkMap.get(hrefBase);
        if (byT) {
          return `<a href="#" data-open="${byT.id}" data-title="${esc(byT.title)}" data-path="${esc(
            byT.rel_path
          )}">${text}</a>`;
        }
      }
      return `<a href="${esc(t)}" class="dangling" title="未解析的链接：${esc(t)}">${text}</a>`;
    },
    image({ href, title, text }) {
      const t = href ?? "";
      const alt = esc(text);
      if (t.startsWith("http://") || t.startsWith("https://") || t.startsWith("data:")) {
        return `<img src="${esc(t)}" alt="${alt}"${title ? ` title="${esc(title)}"` : ""}>`;
      }
      const resolved = resolveRelPath(dir, t);
      if (resolved === null) {
        return `<span class="missing-image" title="图片路径不安全或不存在">[图片：${alt || "无法加载"}]</span>`;
      }
      return `<img src="${esc(rawUrl(resolved))}" alt="${alt}" loading="lazy">`;
    },
  };

  // 每篇文档独立实例（renderer 需要捕获 per-doc 的 dir/linkMap 闭包）。
  const markdown = new Marked({ gfm: true, breaks: true, async: false });
  markdown.use({ renderer });
  return markdown.parse(content) as string;
}

export function Reader({ docId, relPath, onClose, onOpen }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [linkMap, setLinkMap] = useState<Map<string, LinkTarget>>(new Map());
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    setContent(null);
    setError(null);
    setLinkMap(new Map());
    getDocContent(docId)
      .then((text) => alive && setContent(text))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    getNeighbors(docId)
      .then((nb) => {
        const map = new Map<string, LinkTarget>();
        for (const out of nb.outgoing) {
          // 相对链接用原文 target（markdown href 完全一致），wiki 用 [[target]]
          map.set(out.target, { id: out.doc_id, title: out.title, rel_path: out.rel_path });
        }
        alive && setLinkMap(map);
      })
      .catch(() => {
        /* 链接解析失败不影响阅读 */
      });
    return () => {
      alive = false;
    };
  }, [docId]);

  const html = useMemo(
    () => (content !== null ? renderMarkdown({ content, relPath, linkMap }) : ""),
    [content, relPath, linkMap]
  );

  // 事件委托：data-open 链接（相对/WikiLink）→ 打开目标文档；
  // 悬挂链接不参与跳转（只显示 tooltip）。
  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = (e.target as HTMLElement).closest("a[data-open]") as HTMLAnchorElement | null;
    if (target) {
      e.preventDefault();
      const id = Number(target.dataset.open);
      if (Number.isFinite(id)) onOpen(id, target.dataset.path ?? "");
      return;
    }
    if ((e.target as HTMLElement).closest("a.dangling")) {
      e.preventDefault();
    }
  };

  return (
    <article className="reader">
      <header className="reader-header">
        <div className="reader-meta">
          <span className="reader-path" title={relPath}>
            {relPath}
          </span>
          <button className="close" onClick={onClose}>
            返回列表
          </button>
        </div>
      </header>
      {error ? (
        <div className="error">读取失败：{error}</div>
      ) : content === null ? (
        <div className="hint">加载中…</div>
      ) : (
        <div
          ref={containerRef}
          className="markdown-body"
          dangerouslySetInnerHTML={{ __html: html }}
          onClick={handleClick}
        />
      )}
    </article>
  );
}