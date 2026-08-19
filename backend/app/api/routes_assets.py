"""Asset metadata endpoints (thin REST over service layer; files stay under raw/)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from app.api.deps import get_engine_dep
from app.api.models import AssetMeta, ErrorBody
from app.service.assets import asset_by_id, doc_assets

router = APIRouter(tags=["assets"])


def _to_meta(row: dict) -> AssetMeta:
    return AssetMeta(**{**row, "modified_at": row["modified_at"] or None})


@router.get("/documents/{doc_id}/assets", response_model=list[AssetMeta])
def list_document_assets(doc_id: int, engine: Engine = Depends(get_engine_dep)) -> list[AssetMeta]:
    exists, rows = doc_assets(engine, doc_id)
    if not exists:
        raise HTTPException(404, detail=ErrorBody(code="DOC_NOT_FOUND", message=f"文档 {doc_id} 不存在").model_dump())
    return [_to_meta(r) for r in rows]


@router.get("/assets/{asset_id}", response_model=AssetMeta)
def get_asset(asset_id: int, engine: Engine = Depends(get_engine_dep)) -> AssetMeta:
    row = asset_by_id(engine, asset_id)
    if row is None:
        raise HTTPException(404, detail=ErrorBody(code="ASSET_NOT_FOUND", message=f"Asset {asset_id} 不存在").model_dump())
    return _to_meta(row)


__all__ = ["router"]
