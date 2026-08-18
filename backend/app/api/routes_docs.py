"""Document metadata / content / neighbors endpoints."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, text

from app.api.deps import get_engine_dep
from app.api.models import (
    DocumentList,
    DocumentMeta,
    ErrorBody,
    Neighbor,
    NeighborsResponse,
    doc_row_to_meta,
)
from app.config import get_settings

router = APIRouter(tags=["documents"])

_ESCAPE_LIKE_RE = re.compile(r"([\\%_])")
_STATUS_PATTERN = "^(indexed|missing|failed)$"


def _like(value: str) -> str:
    return "%" + _ESCAPE_LIKE_RE.sub(r"\\\1", value) + "%"


def fetch_doc_row(conn, doc_id: int) -> dict | None:
    row = conn.execute(text("SELECT * FROM documents WHERE id = :id"), {"id": doc_id}).mappings().first()
    return dict(row) if row else None


@router.get("/documents", response_model=DocumentList)
def list_documents(
    directory: str | None = Query(None, alias="dir"),
    status: str | None = Query(None, pattern=_STATUS_PATTERN),
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    engine: Engine = Depends(get_engine_dep),
) -> DocumentList:
    conds: list[str] = []
    params: dict = {}
    if directory:
        conds.append("rel_path LIKE :dir ESCAPE '\\'")
        params["dir"] = _like(directory.rstrip("/") + "/")
    if status:
        conds.append("status = :status")
        params["status"] = status
    if q:
        conds.append("(title LIKE :titleq ESCAPE '\\' OR rel_path LIKE :pathq ESCAPE '\\')")
        params["titleq"] = _like(q)
        params["pathq"] = _like(q)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    with engine.connect() as conn:
        total = int(conn.execute(text(f"SELECT count(*) FROM documents{where}"), params).scalar())
        rows = conn.execute(
            text(
                f"SELECT * FROM documents{where} ORDER BY rel_path ASC"
                " LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": limit, "offset": offset},
        ).mappings().all()
    return DocumentList(
        items=[doc_row_to_meta(dict(row)) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{doc_id}", response_model=DocumentMeta)
def get_document(doc_id: int, engine: Engine = Depends(get_engine_dep)) -> DocumentMeta:
    with engine.connect() as conn:
        row = fetch_doc_row(conn, doc_id)
    if row is None:
        raise HTTPException(404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump())
    return doc_row_to_meta(row)


@router.get("/documents/{doc_id}/content")
def get_document_content(doc_id: int, engine: Engine = Depends(get_engine_dep)):
    """Original markdown, always read from raw/ at request time.

    Parsing/rendering is the frontend's job; the database holds no body copy
    (contentless FTS + metadata only), so nothing here can serve stale text.
    """
    from fastapi import Response

    with engine.connect() as conn:
        row = fetch_doc_row(conn, doc_id)
    if row is None:
        raise HTTPException(404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump())

    path = (get_settings().raw_root.resolve() / row["rel_path"]).resolve()
    try:
        path.relative_to(get_settings().raw_root.resolve())
    except ValueError:
        raise HTTPException(500, detail=ErrorBody(code="PATH_ESCAPE", message="文档路径逃逸了 raw/，拒绝读取").model_dump()) from None

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise HTTPException(404, detail=ErrorBody(code="DOC_ON_DISK_MISSING", message=f"磁盘上未找到文件: {exc}").model_dump()) from exc

    return Response(
        content=data,
        media_type="text/markdown; charset=utf-8",
        headers={
            "ETag": f'"{row["sha256"][:16]}"',
            "X-Doc-Sha256": row["sha256"],
            "X-Doc-Status": row["status"],
        },
    )


@router.get("/documents/{doc_id}/neighbors", response_model=NeighborsResponse)
def get_neighbors(doc_id: int, engine: Engine = Depends(get_engine_dep)) -> NeighborsResponse:
    with engine.connect() as conn:
        row = fetch_doc_row(conn, doc_id)
        if row is None:
            raise HTTPException(404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump())
        outgoing = conn.execute(
            text(
                "SELECT d.id AS doc_id, d.rel_path, d.title, l.target, l.kind"
                " FROM links l JOIN documents d ON d.id = l.to_doc"
                " WHERE l.from_doc = :id AND l.to_doc IS NOT NULL"
                " ORDER BY d.rel_path"
            ),
            {"id": doc_id},
        ).mappings().all()
        incoming = conn.execute(
            text(
                "SELECT d.id AS doc_id, d.rel_path, d.title, l.target, l.kind"
                " FROM links l JOIN documents d ON d.id = l.from_doc"
                " WHERE l.to_doc = :id"
                " ORDER BY d.rel_path"
            ),
            {"id": doc_id},
        ).mappings().all()
    return NeighborsResponse(
        incoming=[Neighbor(**dict(r)) for r in incoming],
        outgoing=[Neighbor(**dict(r)) for r in outgoing],
    )


__all__ = ["router"]
