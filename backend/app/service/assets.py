"""Asset list queries（REST 与 MCP 共用）。"""

from __future__ import annotations

from sqlalchemy import Engine, text

from app.service.docs import fetch_doc_row

_ASSET_COLS = ("id, document_id, relative_path, filename, extension, mime_type,"
               " size, sha256, modified_at, status")


def doc_assets(engine: Engine, doc_id: int) -> tuple[bool, list[dict]]:
    """(文档是否存在, 该文档的资产行)。"""
    if fetch_doc_row(engine, doc_id) is None:
        return False, []
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {_ASSET_COLS} FROM assets WHERE document_id = :id ORDER BY relative_path"),
            {"id": doc_id},
        ).mappings().all()
    return True, [dict(r) for r in rows]


def asset_by_id(engine: Engine, asset_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_ASSET_COLS} FROM assets WHERE id = :id"), {"id": asset_id}
        ).mappings().first()
        return dict(row) if row else None


__all__ = ["doc_assets", "asset_by_id"]
