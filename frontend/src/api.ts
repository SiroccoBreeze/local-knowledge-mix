/** Thin typed client for the local-knowledge v1 API. */

export interface DocMeta {
  id: number;
  rel_path: string;
  doc_type: string;
  title: string;
  sha256: string;
  size: number;
  mtime_ns: number;
  word_count: number;
  char_count: number;
  line_count: number;
  frontmatter: Record<string, unknown> | null;
  headings: { level: number; text: string }[];
  first_seen: string;
  last_seen: string;
  last_indexed: string;
  status: string;
  scan_error: string | null;
}

export interface Snippet {
  text: string; // HTML，关键词已包 <mark>
  start_line: number;
  end_line: number;
}

export interface Hit {
  doc: DocMeta;
  score: number;
  snippets: Snippet[];
  matched_terms: string[];
}

export interface SearchResult {
  query: string;
  total: number;
  limit: number;
  offset: number;
  hits: Hit[];
}

export interface Neighbor {
  doc_id: number;
  rel_path: string;
  title: string;
  target: string; // 原文里的链接目标
  kind: "wiki" | "relative" | "url";
}

export interface Neighbors {
  incoming: Neighbor[];
  outgoing: Neighbor[];
}

export interface AssetMeta {
  id: number;
  document_id: number;
  relative_path: string;
  filename: string;
  extension: string;
  mime_type: string;
  size: number;
  sha256: string;
  modified_at: string | null;
  status: string;
}

const BASE = "/api/v1";

async function readJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
    } catch {
      /* keep fallback message */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

/** 全量文档列表（分页兜底，limit 500 封顶的 API 一次性拉完）。 */
export async function listAllDocuments(): Promise<DocMeta[]> {
  const out: DocMeta[] = [];
  let offset = 0;
  for (;;) {
    const page = await readJson<{ items: DocMeta[]; total: number; limit: number }>(
      `${BASE}/documents?limit=500&offset=${offset}`
    );
    out.push(...page.items);
    if (out.length >= page.total) break;
    offset += page.limit;
  }
  return out;
}

export function getDoc(id: number): Promise<DocMeta> {
  return readJson(`${BASE}/documents/${id}`);
}

export function listAssets(docId: number): Promise<AssetMeta[]> {
  return readJson(`${BASE}/documents/${docId}/assets`);
}

export function search(query: string, limit = 50): Promise<SearchResult> {
  return readJson(`${BASE}/search?limit=${limit}&q=${encodeURIComponent(query)}`);
}

export async function getDocContent(id: number): Promise<string> {
  const res = await fetch(`${BASE}/documents/${id}/content`, { cache: "no-store" });
  if (!res.ok) throw new Error(`读取失败 (${res.status})`);
  return res.text();
}

export function getNeighbors(id: number): Promise<Neighbors> {
  return readJson(`${BASE}/documents/${id}/neighbors`);
}

export interface RelatedItem {
  doc_id: number;
  title: string;
  rel_path: string;
  score: number;
  reasons: string[];
}

export interface RelatedResponse {
  document_id: number;
  items: RelatedItem[];
}

export function getRelatedDocuments(docId: number, limit = 10): Promise<RelatedResponse> {
  return readJson(`${BASE}/documents/${docId}/related?limit=${limit}`);
}

/** 图片等媒体文件的安全访问（后端只允许 raw/ 内白名单类型）。 */
export function rawUrl(relPath: string): string {
  return `${BASE}/raw/${relPath}`;
}

export function dirOf(relPath: string): string {
  const i = relPath.lastIndexOf("/");
  return i >= 0 ? relPath.slice(0, i) : "";
}

export function categoryOf(relPath: string): string {
  const i = relPath.indexOf("/");
  return i >= 0 ? relPath.slice(0, i) : "根目录";
}

/** 相对路径解析（拒绝绝对路径与逃逸出 raw/）。返回 null 表示不可用。 */
export function resolveRel(dir: string, href: string): string | null {
  if (href.startsWith("/") || href.startsWith("\\") || /^[a-zA-Z]:/.test(href)) return null;
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