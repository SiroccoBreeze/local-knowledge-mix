"""Idempotent DDL. Mirror of system/schema.md — keep them in sync."""

from __future__ import annotations

from sqlalchemy import Connection, text

# One statement per entry — never concatenate DDL here (schema code splits on
# ";", which breaks virtual tables that contain semicolons in options).
_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY,
    rel_path      TEXT NOT NULL UNIQUE,
    doc_type      TEXT NOT NULL DEFAULT 'markdown',
    title         TEXT NOT NULL DEFAULT '',
    sha256        TEXT NOT NULL,
    mtime_ns      INTEGER NOT NULL,
    size          INTEGER NOT NULL,
    word_count    INTEGER NOT NULL DEFAULT 0,
    char_count    INTEGER NOT NULL DEFAULT 0,
    line_count    INTEGER NOT NULL DEFAULT 0,
    frontmatter   TEXT,
    headings      TEXT NOT NULL DEFAULT '[]',
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    last_indexed  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'missing'
                  CHECK (status IN ('indexed', 'missing', 'failed')),
    scan_error    TEXT
)""",
    """CREATE TABLE IF NOT EXISTS links (
    id       INTEGER PRIMARY KEY,
    from_doc INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target   TEXT NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('wiki', 'relative', 'url')),
    to_doc   INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE (from_doc, target)
)""",
    "CREATE INDEX IF NOT EXISTS ix_links_to ON links(to_doc)",
    # contentless FTS5: index only, no content copy. rowid == documents.id.
    """CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
    title,
    body,
    headings,
    content='',
    tokenize='trigram'
)""",
)

FTS_DDL = _STATEMENTS[-1]


def ensure_schema(conn: Connection) -> None:
    """Create all tables if missing (transaction-safe, idempotent)."""
    for statement in _STATEMENTS:
        conn.execute(text(statement))


def drop_fts(conn: Connection) -> None:
    conn.execute(text("DROP TABLE IF EXISTS docs_fts"))


def create_fts(conn: Connection) -> None:
    conn.execute(text(FTS_DDL))


def get_meta(conn: Connection, key: str) -> str | None:
    row = conn.execute(text("SELECT value FROM meta WHERE key = :k"), {"k": key}).first()
    return row[0] if row else None


def set_meta(conn: Connection, key: str, value: str) -> None:
    conn.execute(
        text(
            "INSERT INTO meta (key, value) VALUES (:k, :v) "
            "ON CONFLICT(key) DO UPDATE SET value = :v"
        ),
        {"k": key, "v": value},
    )


__all__ = ["ensure_schema", "drop_fts", "create_fts", "get_meta", "set_meta"]
