"""Knowledge stats（MCP 与未来健康检查共用）。"""

from __future__ import annotations

from sqlalchemy import Engine, text

from app.db.schema import get_meta


def knowledge_stats(engine: Engine) -> dict:
    with engine.connect() as conn:
        return {
            "document_count": _one(conn, "SELECT count(*) FROM documents"),
            "asset_count": _one(conn, "SELECT count(*) FROM assets"),
            "link_count": _one(conn, "SELECT count(*) FROM links"),
            "indexed_count": _one(conn, "SELECT count(*) FROM documents WHERE status='indexed'"),
            "missing_count": _one(conn, "SELECT count(*) FROM documents WHERE status='missing'"),
            "last_scan_at": get_meta(conn, "last_scan_at"),
        }


def _one(conn, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar())


__all__ = ["knowledge_stats"]
