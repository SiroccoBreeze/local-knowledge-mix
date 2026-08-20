"""Document metadata / content / neighbors endpoints (thin REST over service layer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from app.api.deps import get_engine_dep
from app.api.models import (
    DocumentList,
    DocumentMeta,
    ErrorBody,
    Neighbor,
    NeighborsResponse,
    RelatedItem,
    RelatedResponse,
    doc_row_to_meta,
)
from app.service.docs import DocNotFoundError, fetch_doc_row
from app.service.docs import list_documents as svc_list_documents
from app.service.files import read_raw_bytes
from app.service.links import get_neighbors
from app.service.related import find_related

router = APIRouter(tags=["documents"])


@router.get("/documents", response_model=DocumentList)
def list_documents(
    directory: str | None = Query(None, alias="dir"),
    status: str | None = Query(None, pattern="^(indexed|missing|failed)$"),
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    engine: Engine = Depends(get_engine_dep),
) -> DocumentList:
    rows, total = svc_list_documents(
        engine, directory=directory, status=status, q=q, limit=limit, offset=offset
    )
    return DocumentList(
        items=[doc_row_to_meta(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{doc_id}", response_model=DocumentMeta)
def get_document(doc_id: int, engine: Engine = Depends(get_engine_dep)) -> DocumentMeta:
    row = fetch_doc_row(engine, doc_id)
    if row is None:
        raise HTTPException(404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump())
    return doc_row_to_meta(row)


@router.get("/documents/{doc_id}/content")
def get_document_content(doc_id: int, engine: Engine = Depends(get_engine_dep)):
    """Original markdown, always read from raw/ at request time.

    Content never lives in the database (contentless FTS + metadata only);
    the raw/ read goes through the shared traversal guard.
    """
    from fastapi import Response

    row = fetch_doc_row(engine, doc_id)
    if row is None:
        raise HTTPException(404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump())
    try:
        data = read_raw_bytes(row["rel_path"])
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=ErrorBody(code="DOC_ON_DISK_MISSING", message=str(exc)).model_dump()) from exc

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
def neighbors_endpoint(doc_id: int, engine: Engine = Depends(get_engine_dep)) -> NeighborsResponse:
    try:
        nb = get_neighbors(engine, doc_id, include_broken=False)
    except KeyError:
        raise HTTPException(404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump()) from None
    return NeighborsResponse(
        incoming=[Neighbor(**r) for r in nb["incoming"]],
        outgoing=[Neighbor(**r) for r in nb["outgoing"]],
    )


@router.get("/documents/{doc_id}/related", response_model=RelatedResponse)
def related_endpoint(
    doc_id: int,
    limit: int = Query(10, ge=1, le=50),
    engine: Engine = Depends(get_engine_dep),
) -> RelatedResponse:
    try:
        result = find_related(engine, doc_id, limit=limit)
    except DocNotFoundError:
        raise HTTPException(
            404,
            detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump(),
        ) from None
    return RelatedResponse(
        document_id=result["document_id"],
        items=[RelatedItem(**it) for it in result["items"]],
    )


__all__ = ["router"]
