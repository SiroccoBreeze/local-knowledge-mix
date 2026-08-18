"""Search endpoint: GET /search."""

from __future__ import annotations

from sqlite3 import OperationalError as NativeOperationalError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError as SAOperationalError

from app.api.deps import get_engine_dep
from app.api.models import (
    ErrorBody,
    SearchHit,
    SearchResponse,
    Snippet,
    doc_row_to_meta,
)
from app.search import query as query_mod

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_endpoint(
    q: str = Query(min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    engine: Engine = Depends(get_engine_dep),
) -> SearchResponse:
    if not query_mod.parse_query(q):
        raise HTTPException(
            400,
            detail=ErrorBody(code="EMPTY_QUERY", message=f'查询 "{q}" 没有有效关键词').model_dump(),
        )
    try:
        result = query_mod.search(engine, q, limit=limit, offset=offset)
    except (SAOperationalError, NativeOperationalError) as exc:
        raise HTTPException(
            400,
            detail=ErrorBody(code="BAD_QUERY", message=f"查询语法无效: {exc}").model_dump(),
        ) from exc
    return SearchResponse(
        query=q,
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        hits=[
            SearchHit(
                doc=doc_row_to_meta(hit.doc),
                score=hit.score,
                snippets=[Snippet(text=s.text, start_line=s.start_line, end_line=s.end_line) for s in hit.snippets],
            )
            for hit in result.hits
        ],
    )


__all__ = ["router"]
