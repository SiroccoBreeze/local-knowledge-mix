"""SQLite engine + connection management.

The database is a *derived artifact*: it stores only metadata, headings,
frontmatter, links and the contentless FTS index. Markdown bodies always live
on disk under raw/.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from app.config import get_settings


def get_engine() -> Engine:
    """Create (and cache) the engine for `get_settings().db_path`.

    Data directory creation is allowed: the db is derived (invariant #2).
    raw/ is never touched here.
    """
    path = Path(get_settings().db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"timeout": 30},
        # One engine per process is enough for phase 1.
        pool_pre_ping=True,
    )


def _set_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


event.listen(Engine, "connect", _set_pragmas)

__all__ = ["get_engine"]
