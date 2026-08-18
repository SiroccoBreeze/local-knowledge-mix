"""Pydantic response models for the API layer."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def _load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


class ScanReportModel(BaseModel):
    started_at: str
    finished_at: str
    duration_ms: int
    raw_root: str
    full: bool
    total_docs: int
    added: int
    changed: int
    unchanged: int
    skipped: int
    missing: int
    failed: int


class DocumentMeta(BaseModel):
    id: int
    rel_path: str
    doc_type: str
    title: str
    sha256: str
    size: int
    mtime_ns: int
    word_count: int
    char_count: int
    line_count: int
    frontmatter: dict | None
    headings: list[dict]
    first_seen: str
    last_seen: str
    last_indexed: str
    status: str
    scan_error: str | None


class DocumentList(BaseModel):
    items: list[DocumentMeta]
    total: int
    limit: int
    offset: int


class Snippet(BaseModel):
    text: str
    start_line: int
    end_line: int


class SearchHit(BaseModel):
    doc: DocumentMeta
    score: float
    snippets: list[Snippet]


class SearchResponse(BaseModel):
    query: str
    total: int
    limit: int
    offset: int
    hits: list[SearchHit]


class Neighbor(BaseModel):
    doc_id: int
    rel_path: str
    title: str
    target: str  # the raw link target as written in the source document
    kind: str


class NeighborsResponse(BaseModel):
    incoming: list[Neighbor]
    outgoing: list[Neighbor]


class HealthResponse(BaseModel):
    status: str  # "ok" | "error"
    db: str
    last_scan_at: str | None
    last_scan_report: ScanReportModel | None


class AssetMeta(BaseModel):
    id: int
    document_id: int
    relative_path: str
    filename: str
    extension: str
    mime_type: str
    size: int
    sha256: str
    modified_at: str | None
    status: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


def doc_row_to_meta(row: dict[str, Any]) -> DocumentMeta:
    return DocumentMeta(
        id=row["id"],
        rel_path=row["rel_path"],
        doc_type=row["doc_type"],
        title=row["title"],
        sha256=row["sha256"],
        size=row["size"],
        mtime_ns=row["mtime_ns"],
        word_count=row["word_count"],
        char_count=row["char_count"],
        line_count=row["line_count"],
        frontmatter=_load_json(row.get("frontmatter"), None),
        headings=_load_json(row.get("headings"), []),
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        last_indexed=row["last_indexed"],
        status=row["status"],
        scan_error=row.get("scan_error"),
    )


__all__ = [
    "ScanReportModel",
    "DocumentMeta",
    "DocumentList",
    "Snippet",
    "SearchHit",
    "SearchResponse",
    "Neighbor",
    "NeighborsResponse",
    "AssetMeta",
    "HealthResponse",
    "ErrorBody",
    "ErrorResponse",
    "doc_row_to_meta",
]
