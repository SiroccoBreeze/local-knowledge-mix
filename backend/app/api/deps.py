"""FastAPI dependency helpers."""

from __future__ import annotations

from sqlalchemy import Engine

from app.db.engine import get_engine


def get_engine_dep() -> Engine:
    """Engine for the process (tests override this dependency)."""
    return get_engine()


__all__ = ["get_engine_dep"]
