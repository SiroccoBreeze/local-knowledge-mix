"""Asset metadata endpoints (files themselves stay under raw/)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine, text

from app.api.deps import get_engine_dep
from app.api.models import AssetMeta, ErrorBody

router = APIRouter(tags=["assets"])

_ASSET_COLS = "id, document_id, relative_path, filename, extension, mime_type, size, sha256, modified_at, status"


def _asset_list(rows) -> list[AssetMeta]:
    return [AssetMeta(**{**dict(r), "modified_at": r["modified_at"] or None}) for r in rows]


def _row_to_meta(row) -> AssetMeta:
    d = dict(row)
    return AssetMeta(**{**d, "modified_at": d["modified_at"] or None})


@router.get("/documents/{doc_id}/assets", response_model=list[AssetMeta])
def list_document_assets(doc_id: int, engine: Engine = Depends(get_engine_dep)) -> list[AssetMeta]:
    with engine.connect() as conn:
        doc = conn.execute(
            text("SELECT id FROM documents WHERE id = :id"), {"id": doc_id}
        ).first()
        if doc is None:
            raise HTTPException(
                404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump()
            )
        rows = conn.execute(
            text(f"SELECT {_ASSET_COLS} FROM assets WHERE document_id = :id ORDER BY relative_path"),
            {"id": doc_id},
        ).mappings().all()
    return _asset_list(rows)


@router.get("/assets/{asset_id}", response_model=AssetMeta)
def get_asset(asset_id: int, engine: Engine = Depends(get_engine_dep)) -> AssetMeta:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_ASSET_COLS} FROM assets WHERE id = :id"), {"id": asset_id}
        ).mappings().first()
    if row is None:
        raise HTTPException(
            404, detail=ErrorBody(code="ASSET_NOT_FOUND", message=f"Asset {asset_id} 不存在").model_dump()
        )
    return _row_to_meta(row)


__all__ = ["router"]
