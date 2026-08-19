"""MCP tool implementations. 只读 —— 复用 service / search / scanner 能力。

不暴露原始 SQL、不读取 raw/ 之外的文件、不新增任意文件读取工具。
"""

from __future__ import annotations

import html

from sqlalchemy import Engine

from app.search.query import search as fts_search
from app.service.assets import doc_assets
from app.service.docs import DocNotFoundError, fetch_doc_row, list_documents, read_document
from app.service.links import get_neighbors
from app.service.stats import knowledge_stats


class ToolError(ValueError):
    """MCP 工具业务错误（由 FastMCP 转成 isError 结果返回）。"""


def _require_doc(engine: Engine, doc_id: int) -> None:
    if fetch_doc_row(engine, doc_id) is None:
        raise ToolError(f"文档 {doc_id} 不存在")


def search_documents_tool(
    engine: Engine,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """FTS5 全文检索（复用现有 search 逻辑，snippet 转纯文本供 LLM 使用）。"""
    if not query.strip():
        return {"query": query, "total": 0, "hits": []}
    try:
        result = fts_search(engine, query, limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001 — 查询语法错误转成友好提示
        raise ToolError(f"查询语法无效: {exc}") from exc
    hits = [
        {
            "doc_id": hit.doc["id"],
            "title": hit.doc["title"],
            "rel_path": hit.doc["rel_path"],
            "score": hit.score,
            "snippets": [
                {
                    "text": html.unescape(s.text.replace("<mark>", "").replace("</mark>", "")),
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                }
                for s in hit.snippets
            ],
        }
        for hit in result.hits
    ]
    return {"query": query, "total": result.total, "hits": hits}


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
    "get_knowledge_stats_tool",
]
