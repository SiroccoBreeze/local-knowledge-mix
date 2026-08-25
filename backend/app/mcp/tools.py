"""MCP tool implementations. 只读 —— 复用 service / search / scanner 能力。

不暴露原始 SQL、不读取 raw/ 之外的文件、不新增任意文件读取工具。
"""

from __future__ import annotations

import html

from sqlalchemy import Engine

from app.retrieval.context import merge_contexts
from app.retrieval.contract import related_retrieval, search_retrieval
from app.search.query import search as fts_search
from app.service.assets import doc_assets
from app.service.docs import DocNotFoundError, fetch_doc_row, list_documents, read_document
from app.service.links import get_neighbors
from app.service.related import find_related
from app.service.stats import knowledge_stats

SEARCH_MODES = ("smart", "keyword")


class ToolError(ValueError):
    """MCP 工具业务错误（由 FastMCP 转成结构化错误返回，不泄漏 SQLite 异常）。"""


def _require_doc(engine: Engine, doc_id: int) -> None:
    if fetch_doc_row(engine, doc_id) is None:
        raise ToolError(f"文档 {doc_id} 不存在")


def _plain_snippet(text_html: str) -> str:
    """snippet HTML（含 <mark>）→ 纯文本（MCP 消费者是 LLM，不要 HTML）。"""
    return html.unescape(text_html.replace("<mark>", "").replace("</mark>", ""))


def search_documents_tool(
    engine: Engine,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
    search_mode: str = "smart",
) -> dict:
    """FTS5 全文检索（复用 search/query.search）。

    smart（默认）：Phase 4–5 重排 —— score 越高越相关、带 matched_terms、多词 snippet；
    keyword：legacy 行为完全一致（原始 bm25 序，无 matched_terms）。
    """
    if not query.strip():
        return {"query": query, "search_mode": search_mode, "total": 0, "hits": []}
    if search_mode not in SEARCH_MODES:
        raise ToolError(f"未知 search_mode {search_mode!r}，仅支持 smart / keyword")
    try:
        result = fts_search(engine, query, limit=limit, offset=offset, mode=search_mode)
    except Exception as exc:  # noqa: BLE001 — FTS 语法错误 -> 友好提示
        raise ToolError(f"查询语法无效: {exc}") from exc

    hits = []
    for hit in result.hits:
        item = {
            "doc_id": hit.doc["id"],
            "title": hit.doc["title"],
            "rel_path": hit.doc["rel_path"],
            "score": hit.score,
            "snippets": [
                {
                    "text": _plain_snippet(s.text),
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                }
                for s in hit.snippets
            ],
        }
        if search_mode == "smart":
            item["matched_terms"] = hit.matched_terms
        hits.append(item)
    return {"query": query, "search_mode": search_mode, "total": result.total, "hits": hits}


def get_document_tool(engine: Engine, document_id: int) -> dict:
    """文档全文：元数据来自索引，正文永远从 raw/ 当前文件读取。"""
    try:
        doc = read_document(engine, document_id)
    except DocNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except FileNotFoundError as exc:  # 索引在但文件已被删除
        raise ToolError(f"文档 {document_id} 的正文在磁盘上不存在（文件已删除？）: {exc}") from exc
    return {
        "id": doc["id"],
        "title": doc["title"],
        "rel_path": doc["rel_path"],
        "status": doc["status"],
        "sha256": doc["sha256"],
        "frontmatter": doc["frontmatter"],
        "headings": doc["headings"],
        "knowledge_status": doc.get("knowledge_status"),
        "content": doc["content"],
    }


def list_documents_tool(
    engine: Engine,
    *,
    q: str | None = None,
    dir: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """文档列表（标题/路径过滤或目录/状态过滤，同 REST /documents）。"""
    rows, total = list_documents(
        engine, directory=dir, status=status, q=q, limit=limit, offset=offset
    )
    return {
        "total": total,
        "items": [
            {
                "id": r["id"],
                "title": r["title"],
                "rel_path": r["rel_path"],
                "status": r["status"],
            }
            for r in rows
        ],
    }


def get_document_links_tool(engine: Engine, document_id: int) -> dict:
    """进出链。断链（to_doc=NULL）明确标记 broken；wiki/待解析目标保留原文 target。"""
    _require_doc(engine, document_id)
    nb = get_neighbors(engine, document_id, include_broken=True)

    def _out(row: dict) -> dict:
        ext = row["kind"] == "url"
        broken = not ext and row.get("to_doc") is None
        return {
            "target": row["target"],
            "kind": row["kind"],
            "broken": broken,
            "external": ext,
            "to_doc": (
                {"id": row["doc_id"], "title": row["title"], "rel_path": row["rel_path"]}
                if row.get("to_doc") is not None
                else None
            ),
        }

    return {
        "document_id": document_id,
        "outgoing": [_out(r) for r in nb["outgoing"]],
        "incoming": [
            {"doc_id": r["doc_id"], "title": r["title"], "rel_path": r["rel_path"], "via_target": r["target"]}
            for r in nb["incoming"]
        ],
    }


def get_document_assets_tool(engine: Engine, document_id: int) -> dict:
    """documents 关联的资产索引（文件本体只在 raw/，工具只给元数据）。"""
    _require_doc(engine, document_id)
    exists, rows = doc_assets(engine, document_id)
    if not exists:
        raise ToolError(f"文档 {document_id} 不存在")
    return {
        "document_id": document_id,
        "items": [
            {
                "id": r["id"],
                "filename": r["filename"],
                "relative_path": r["relative_path"],
                "extension": r["extension"],
                "mime_type": r["mime_type"],
                "size": r["size"],
                "sha256": r["sha256"],
                "status": r["status"],
            }
            for r in rows
        ],
    }


def find_related_documents_tool(engine: Engine, document_id: int, limit: int = 10) -> dict:
    """相关文档（复用 service.related，可解释综合相关性）。"""
    try:
        return find_related(engine, document_id, limit=limit)
    except DocNotFoundError as exc:
        raise ToolError(str(exc)) from exc


def retrieve_context_tool(
    engine: Engine,
    query: str | None = None,
    *,
    limit: int = 8,
    include_related: bool = True,
    document_id: int | None = None,
    max_chars: int = 12000,
    search_mode: str = "smart",
) -> dict:
    """检索知识库并返回经 Context Builder 安全清洗的纯文本 AI Context。"""
    results = []
    total = 0

    if query and query.strip():
        sr = search_retrieval(engine, query, limit=limit, mode=search_mode)
        total = sr.total
        results.append(sr)

    if document_id is not None and include_related:
        try:
            rr = related_retrieval(engine, document_id, limit=limit)
            results.append(rr)
        except DocNotFoundError as exc:
            if not results:
                raise ToolError(f"文档 {document_id} 不存在") from exc

    if not results:
        if not query or not query.strip():
            raise ToolError("查询词不可为空")
        raise ToolError("未检索到结果")

    context = merge_contexts(results, max_docs=limit, max_chars=max_chars)

    seen: set[int] = set()
    items = []
    for r in results:
        for it in r.items:
            if it.document_id not in seen:
                seen.add(it.document_id)
                items.append({"doc_id": it.document_id, "title": it.title, "rel_path": it.rel_path, "score": it.score})

    return {"query": query or "", "total": total, "items": items[:limit], "context": context}


def get_knowledge_stats_tool(engine: Engine) -> dict:
    """知识库整体统计（纯索引元数据）。"""
    return knowledge_stats(engine)


__all__ = [
    "ToolError",
    "search_documents_tool",
    "get_document_tool",
    "list_documents_tool",
    "get_document_links_tool",
    "get_document_assets_tool",
    "find_related_documents_tool",
    "retrieve_context_tool",
    "get_knowledge_stats_tool",
]
