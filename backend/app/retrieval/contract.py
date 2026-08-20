"""V0.6 Phase 11 — 统一 Retrieval Contract（AI Retrieval 数据协议）。

search 与 related 的"出口"被归一为同一种内部结构，供未来的 Context Builder /
retrieve_context MCP 消费。**算法不在此复制**：search/related 照旧走
service/search 层，这里只做结果表达与安全裁剪：

- 永不包含绝对路径 / raw 根 / SQLite 路径 / SQL / 文件系统内部信息；
- score 语义：smart = 越大越相关；keyword 原始 bm25 原样透传（仅兼容模式，不强行转换）；
- source_type 携带 doc_type（当前恒为 markdown，为 sources/ 预留）。
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, field

from sqlalchemy import Engine, text

from app.search.query import SearchResult, Snippet
from app.service.docs import knowledge_status_of
from app.service.related import find_related

REASON_LABELS: dict[str, str] = {
    "linked": "有链接关系",
    "same_directory": "同目录",
    "shared_tag": "共同标签",
    "title_similarity": "标题相似",
    "heading_similarity": "章节相似",
    "term_similarity": "内容相关",
}


@dataclass(frozen=True)
class RetrievalReason:
    key: str    # machine 值：same_directory / linked / …
    label: str  # human 值：同目录 / 有链接关系 / …


@dataclass(frozen=True)
class RetrievalItem:
    """单条检索结果（文档级）。"""

    document_id: int
    title: str
    rel_path: str
    score: float
    matched_terms: list[str] = field(default_factory=list)
    snippets: list[Snippet] = field(default_factory=list)
    reasons: list[RetrievalReason] = field(default_factory=list)
    knowledge_status: str | None = None
    source_type: str = "markdown"


@dataclass(frozen=True)
class RetrievalResult:
    """一次检索的完整结果（search 或 related 的归一化表达）。"""

    kind: str                       # "search" | "related"
    mode: str                       # "smart" | "keyword"（related 固定 "related"）
    query: str | None
    anchor_document_id: int | None
    total: int
    items: list[RetrievalItem]
    limit: int
    offset: int = 0


@dataclass(frozen=True)
class RetrievalContextItem:
    document_id: int
    title: str
    rel_path: str
    snippet_text: str   # 纯文本（已去 <mark>），面向 LLM 消费
    score: float
    knowledge_status: str | None


@dataclass(frozen=True)
class RetrievalContext:
    """Context Pack 切片（Phase 12 Context Builder 的输入形状）。"""

    kind: str
    total: int
    items: list[RetrievalContextItem]


# ---------- 适配器：现有结果 → 统一结构 ----------


def _reason_of(key: str) -> RetrievalReason:
    return RetrievalReason(key=key, label=REASON_LABELS.get(key, key))


def _status_from_row(doc: dict) -> str | None:
    raw = doc.get("frontmatter")
    if isinstance(raw, dict):
        return knowledge_status_of(raw)
    if isinstance(raw, str) and raw:
        try:
            return knowledge_status_of(json.loads(raw))
        except (ValueError, TypeError):
            return None
    return None


def from_search(result: SearchResult, *, mode: str = "smart") -> RetrievalResult:
    items = [
        RetrievalItem(
            document_id=h.doc["id"],
            title=h.doc["title"],
            rel_path=h.doc["rel_path"],
            score=h.score,
            matched_terms=h.matched_terms,
            snippets=h.snippets,
            knowledge_status=_status_from_row(h.doc),
            source_type=h.doc.get("doc_type") or "markdown",
        )
        for h in result.hits
    ]
    return RetrievalResult(
        kind="search",
        mode=mode,
        query=result.query,
        anchor_document_id=None,
        total=result.total,
        items=items,
        limit=result.limit,
        offset=result.offset,
    )


def from_related(engine: Engine, payload: dict) -> RetrievalResult:
    """service.related 的 dict 结果 → 统一结构（批量补齐 knowledge_status）。"""
    ids = [it["doc_id"] for it in payload["items"]]
    status_map: dict[int, str | None] = {}
    if ids:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, frontmatter FROM documents WHERE id IN"
                    " (SELECT value FROM json_each(:ids))"
                ),
                {"ids": json.dumps(ids)},
            ).mappings().all()
        for row in rows:
            raw = row["frontmatter"]
            try:
                fm = json.loads(raw) if raw else None
            except (ValueError, TypeError):
                fm = None
            status_map[row["id"]] = knowledge_status_of(fm)

    items = [
        RetrievalItem(
            document_id=it["doc_id"],
            title=it["title"],
            rel_path=it["rel_path"],
            score=it["score"],
            reasons=[_reason_of(k) for k in it["reasons"]],
            knowledge_status=status_map.get(it["doc_id"]),
            source_type="markdown",
        )
        for it in payload["items"]
    ]
    return RetrievalResult(
        kind="related",
        mode="related",
        query=None,
        anchor_document_id=payload["document_id"],
        total=len(payload["items"]),
        items=items,
        limit=len(payload["items"]),
    )


# ---------- 组合入口（Phase 12 Context Builder 的调用面） ----------


def search_retrieval(
    engine: Engine, q: str, *, limit: int = 20, offset: int = 0, mode: str = "smart"
) -> RetrievalResult:
    from app.search.query import search as fts_search

    return from_search(fts_search(engine, q, limit=limit, offset=offset, mode=mode), mode=mode)


def related_retrieval(engine: Engine, document_id: int, *, limit: int = 10) -> RetrievalResult:
    return from_related(engine, find_related(engine, document_id, limit=limit))


# ---------- Context Pack 切片 ----------


def _plain_snippet(snippet: Snippet) -> str:
    return html.unescape(snippet.text.replace("<mark>", "").replace("</mark>", ""))


def to_context(result: RetrievalResult) -> RetrievalContext:
    items = [
        RetrievalContextItem(
            document_id=item.document_id,
            title=item.title,
            rel_path=item.rel_path,
            snippet_text=_plain_snippet(item.snippets[0]) if item.snippets else "",
            score=item.score,
            knowledge_status=item.knowledge_status,
        )
        for item in result.items
    ]
    return RetrievalContext(kind=result.kind, total=result.total, items=items)


def to_dict(obj) -> dict:
    """JSON 友好的 dict（含嵌套 dataclass 与 snippets）。"""
    return asdict(obj)


__all__ = [
    "RetrievalReason",
    "RetrievalItem",
    "RetrievalResult",
    "RetrievalContext",
    "RetrievalContextItem",
    "from_search",
    "from_related",
    "search_retrieval",
    "related_retrieval",
    "to_context",
    "to_dict",
]
