/** Markdown 渲染管线（V0.3.5）：
 *  front matter 剥离 → Wiki 预处理 → marked 自定义渲染。
 * 内容层与 React 组件解耦，Reader 与 ShareView 共用。
 */

import { Marked, type RendererObject, type Token } from "marked";
import type { MouseEvent } from "react";

import { dirOf, rawUrl } from "./api";
import type { LinkTarget } from "./docview";

export const WIKI_SCHEME = "lk-wiki:";

/** 解码常见 HTML 实体（内容里混入的 &quot; 等），再统一转义一次，
 *  避免 &quot; 原样/双重转义出现在正文。 */
function clean(raw: string): string {
  return raw
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

/** 先解码实体再转义 —— 保证最终输出恰一层转义。 */
function esc(s: string): string {
  return clean(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\s_-]/gu, "")
    .replace(/\s+/g, "-");
}

/** YAML front matter 从正文剥离（不渲染；元数据由后端 meta 提供）。
 *  未闭合的 --- 不做处理（保持内容完整）。 */
export function stripFrontmatter(md: string): string {
  if (!/^---\r?\n/.test(md)) return md;
  const lines = md.split(/\r?\n/);
  const cap = Math.min(lines.length, 80);
  for (let i = 1; i < cap; i++) {
    if (/^---[ \t]*$/.test(lines[i])) {
      return lines.slice(i + 1).join("\n");
    }
  }
  return md;
}

/** 把 marked 行内 token 摊平成纯文本（用于标题 id 与链接文字）。 */
function tokenText(t: string | Token): string {
  if (typeof t === "string") return t;
  if (Array.isArray((t as { tokens?: Token[] }).tokens)) {
    return (t as { tokens: Token[] }).tokens.map(tokenText).join("");
  }
  return (t as { text?: string }).text ?? "";
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

/** 渲染 markdown → HTML（GFM；图片/相对链接走本地安全访问；代码块带复制按钮）。 */
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
    code({ text, lang }) {
      const label = lang ? `<span class="code-lang">${esc(clean(lang))}</span>` : "";
      return (
        `<div class="code-wrap">` +
        `<div class="code-bar">${label}<button class="code-copy" type="button">复制</button></div>` +
        `<pre><code>${clean(text)}</code></pre></div>`
      );
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
      return `<img class="md-img" src="${esc(rawUrl(resolved))}" alt="${esc(text)}" loading="lazy">`;
    },
  };

  // 每篇文档独立实例（renderer 需要捕获 per-doc 的 dir/linkMap 闭包）。
  const markdown = new Marked({ gfm: true, breaks: true, async: false });
  markdown.use({ renderer });
  return markdown.parse(content) as string;
}

/** 阅读主区域点击处理：文档跳转 / 代码复制 / 图片灯箱统一分发。 */
export type ReaderClick = { said?: "navigate" | "copy" | "zoom"; id?: number; relPath?: string; text?: string; src?: string; alt?: string };

export function handleBodyClick(e: MouseEvent<HTMLDivElement>): ReaderClick | null {
  const el = e.target as HTMLElement;
  const openLink = el.closest("a[data-open]") as HTMLAnchorElement | null;
  if (openLink) {
    e.preventDefault();
    const id = Number(openLink.dataset.open);
    return { said: "navigate", id: Number.isFinite(id) ? id : undefined, relPath: openLink.dataset.path ?? "" };
  }
  if (el.closest("a.dangling")) {
    e.preventDefault();
    return null;
  }
  const copyBtn = el.closest("button.code-copy") as HTMLButtonElement | null;
  if (copyBtn) {
    e.preventDefault();
    const pre = copyBtn.closest(".code-wrap")?.querySelector("pre code");
    return { said: "copy", text: pre?.textContent ?? "" };
  }
  if ((el as HTMLImageElement).tagName === "IMG" && el.className === "md-img") {
    e.preventDefault();
    return { said: "zoom", src: (el as HTMLImageElement).src, alt: (el as HTMLImageElement).alt };
  }
  return null;
}