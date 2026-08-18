"""SQLite + FTS5 sync primitives — the *only* writer side of the system.

Every function runs inside the caller's single SQLAlchemy transaction, so the
metadata rows and the contentless FTS index stay atomic.
"""

from __future__ import annotations

import json
import posixpath

from sqlalchemy import Connection, text

from app.scanner.parse import ParsedDoc

_FTS_COLUMNS = "(docs_fts, rowid, title, body, headings)"


def fts_has(conn: Connection, doc_id: int) -> bool:
    """Whether the contentless FTS table already indexes this rowid.

    The 'delete' command must NEVER be issued for a missing rowid inside a
    transaction: on SQLite 3.37 it corrupts the file ("disk image is malformed").
    Every delete below is guarded by this check.
    """
    row = conn.execute(text("SELECT rowid FROM docs_fts WHERE rowid = :id"), {"id": doc_id}).first()
    return row is not None


def replace_doc(conn: Connection, doc_id: int, pd: ParsedDoc) -> None:
    """contentless FTS update: 'delete' (if present) then re-INSERT same rowid."""
    values = {
        "id": doc_id,
        "t": pd.title,
        "b": pd.plain_text,
        "h": " ".join(h["text"] for h in pd.headings),
    }
    if fts_has(conn, doc_id):
        conn.execute(
            text(
                f"INSERT INTO docs_fts {_FTS_COLUMNS} "
                "VALUES ('delete', :id, :t, :b, :h)"
            ),
            values,
        )
    conn.execute(
        text(
            "INSERT INTO docs_fts (rowid, title, body, headings) "
            "VALUES (:id, :t, :b, :h)"
        ),
        values,
    )


def drop_doc_fts(conn: Connection, doc_id: int) -> None:
    if fts_has(conn, doc_id):
        conn.execute(
            text(f"INSERT INTO docs_fts {_FTS_COLUMNS} VALUES ('delete', :id, '', '', '')"),
            {"id": doc_id},
        )


def insert_doc(conn: Connection, fi, sha: str, pd: ParsedDoc, now: str, *, doc_id: int | None = None) -> int:
    """Write metadata (+ FTS row). With doc_id, updates in place (rename/repair)."""
    row = {
        "rel_path": fi.rel_path,
        "title": pd.title,
        "sha256": sha,
        "mtime_ns": fi.mtime_ns,
        "size": fi.size,
        "word_count": pd.word_count,
        "char_count": pd.char_count,
        "line_count": pd.line_count,
        "frontmatter": (
            json.dumps(pd.frontmatter, ensure_ascii=False, default=str) if pd.frontmatter else None
        ),
        "headings": json.dumps(pd.headings, ensure_ascii=False),
        "now": now,
        "scan_error": pd.scan_error,
    }
    if doc_id is not None:
        row["id"] = doc_id
        conn.execute(
            text(
                "UPDATE documents SET rel_path=:rel_path, title=:title, sha256=:sha256,"
                " mtime_ns=:mtime_ns, size=:size, word_count=:word_count,"
                " char_count=:char_count, line_count=:line_count, frontmatter=:frontmatter,"
                " headings=:headings, last_seen=:now, last_indexed=:now, status='indexed',"
                " scan_error=:scan_error WHERE id=:id"
            ),
            row,
        )
        replace_doc(conn, doc_id, pd)
        return doc_id

    result = conn.execute(
        text(
            "INSERT INTO documents (rel_path, doc_type, title, sha256, mtime_ns, size,"
            " word_count, char_count, line_count, frontmatter, headings, first_seen,"
            " last_seen, last_indexed, status, scan_error) VALUES (:rel_path, 'markdown',"
            " :title, :sha256, :mtime_ns, :size, :word_count, :char_count, :line_count,"
            " :frontmatter, :headings, :now, :now, :now, 'indexed', :scan_error)"
        ),
        row,
    )
    new_id = int(result.lastrowid)
    replace_doc(conn, new_id, pd)
    return new_id


def mark_failed(conn: Connection, fi, prev, error: str, now: str) -> None:
    if prev is not None:
        conn.execute(
            text(
                "UPDATE documents SET status='failed', scan_error=:error,"
                " mtime_ns=:mtime_ns, size=:size, last_indexed=:now, last_seen=:now WHERE id=:id"
            ),
            {"id": prev["id"], "error": error, "mtime_ns": fi.mtime_ns, "size": fi.size, "now": now},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO documents (rel_path, doc_type, title, sha256, mtime_ns, size,"
                " first_seen, last_seen, last_indexed, status, scan_error)"
                " VALUES (:rel_path, 'markdown', :rel_path, '', :mtime_ns, :size,"
                " :now, :now, :now, 'failed', :error)"
            ),
            {"rel_path": fi.rel_path, "mtime_ns": fi.mtime_ns, "size": fi.size, "now": now, "error": error},
        )


def mark_missing(conn: Connection, seen: set[str], now: str) -> None:
    """Rows not seen in this walk become 'missing'. Their rows/FTS index are kept
    (audit trail; search already filters them out)."""
    if seen:
        conn.execute(
            text(
                "UPDATE documents SET status='missing', last_indexed=:now"
                " WHERE status != 'missing' AND rel_path NOT IN"
                " (SELECT value FROM json_each(:seen))"
            ),
            {"seen": json.dumps(sorted(seen), ensure_ascii=False), "now": now},
        )
    else:
        conn.execute(
            text("UPDATE documents SET status='missing', last_indexed=:now WHERE status != 'missing'"),
            {"now": now},
        )


def link_maps(conn: Connection) -> dict[str, dict]:
    """Lookup tables for link resolution: rel_path / title / basename / stem."""
    rows = conn.execute(text("SELECT id, rel_path, title FROM documents")).mappings().all()
    by_rel: dict[str, int] = {}
    by_title: dict[str, list[int]] = {}
    by_basename: dict[str, list[int]] = {}
    by_stem: dict[str, list[int]] = {}
    for row in rows:
        path = row["rel_path"]
        by_rel[path] = row["id"]
        by_title.setdefault(row["title"].lower(), []).append(row["id"])
        base = path.rsplit("/", 1)[-1]
        by_basename.setdefault(base, []).append(row["id"])
        stem = base[:-3] if base.lower().endswith(".md") else base
        by_stem.setdefault(stem, []).append(row["id"])
    return {"by_rel": by_rel, "by_title": by_title, "by_basename": by_basename, "by_stem": by_stem}


def resolve_target(kind: str, target: str, src_rel: str, maps: dict[str, dict]) -> int | None:
    """Resolve one link to a documents.id (None = dangling target)."""
    if kind == "relative":
        norm = posixpath.normpath(posixpath.join(posixpath.dirname(src_rel), target))
        if norm.startswith(("..", "/")):
            return None  # escapes raw/ or absolute
        return maps["by_rel"].get(norm)

    t = target.strip()
    t_stem = t[:-3] if t.lower().endswith(".md") else t
    for cand in (t, t_stem):
        if cand in maps["by_rel"]:
            return maps["by_rel"][cand]
    for cand in (t, t_stem):
        if len(maps["by_basename"].get(cand, [])) == 1:
            return maps["by_basename"][cand][0]
        if len(maps["by_stem"].get(cand, [])) == 1:
            return maps["by_stem"][cand][0]
    for cand in (t, t_stem):
        bucket = maps["by_title"].get(cand.lower(), [])
        if len(bucket) == 1:
            return bucket[0]
    return None


def insert_links(
    conn: Connection,
    pending: list[tuple[int, str, str, str]],  # (from_doc, src_rel, kind, target)
    maps: dict[str, dict],
) -> None:
    if not pending:
        return
    conn.execute(
        text(
            "INSERT OR IGNORE INTO links (from_doc, target, kind, to_doc)"
            " VALUES (:f, :t, :k, :to)"
        ),
        [
            {"f": from_doc, "t": target, "k": kind, "to": resolve_target(kind, target, src_rel, maps)}
            for from_doc, src_rel, kind, target in pending
        ],
    )


def detect_renames(conn: Connection, added_files: dict[str, tuple[object, ParsedDoc]], now: str) -> int:
    """Match 'missing' docs to newly-added files with the same content hash.

    Applied only when the pairing is unique on both sides (1:1). Keeps the old
    documents.id, so FTS rowid history and links stay valid.
    Returns the number of renames applied.
    """
    missing = (
        conn.execute(text("SELECT id, rel_path, sha256 FROM documents WHERE status='missing'"))
        .mappings()
        .all()
    )
    missing_shas = [m["sha256"] for m in missing]
    pairs: list[tuple[int, str, str, object, ParsedDoc]] = []
    for m in missing:
        sha = m["sha256"]
        # Dict keys are unique by construction; require 1:1 on the missing side.
        if sha and sha in added_files and missing_shas.count(sha) == 1:
            fi, pd = added_files[sha]
            pairs.append((m["id"], m["rel_path"], sha, fi, pd))

    renamed = 0
    for old_id, _old_rel, sha, fi, pd in pairs:
        new_row = conn.execute(
            text("SELECT id FROM documents WHERE rel_path = :p"), {"p": fi.rel_path}
        ).first()
        if new_row is None:
            continue
        new_id = new_row[0]
        # Content is identical (sha match), so the freshly-added row's own
        # links are a byte-identical copy of the surviving row's. Drop them —
        # moving them over would violate UNIQUE(from_doc, target).
        conn.execute(text("DELETE FROM links WHERE from_doc = :n"), {"n": new_id})
        # Links *from other docs* that resolved to the new path follow the id.
        conn.execute(text("UPDATE links SET to_doc=:o WHERE to_doc=:n"), {"o": old_id, "n": new_id})
        # drop the throwaway new row + its FTS index (no FKs involved).
        drop_doc_fts(conn, new_id)
        conn.execute(text("DELETE FROM documents WHERE id=:n"), {"n": new_id})
        # move the surviving row onto the new path / fresh parse.
        conn.execute(
            text(
                "UPDATE documents SET rel_path=:p, title=:title, sha256=:sha256,"
                " mtime_ns=:mtime_ns, size=:size, word_count=:word_count,"
                " char_count=:char_count, line_count=:line_count, frontmatter=:frontmatter,"
                " headings=:headings, last_seen=:now, last_indexed=:now, status='indexed',"
                " scan_error=:scan_error WHERE id=:o"
            ),
            {
                "p": fi.rel_path,
                "title": pd.title,
                "sha256": sha,
                "mtime_ns": fi.mtime_ns,
                "size": fi.size,
                "word_count": pd.word_count,
                "char_count": pd.char_count,
                "line_count": pd.line_count,
                "frontmatter": (
                    json.dumps(pd.frontmatter, ensure_ascii=False, default=str)
                    if pd.frontmatter
                    else None
                ),
                "headings": json.dumps(pd.headings, ensure_ascii=False),
                "now": now,
                "scan_error": pd.scan_error,
                "o": old_id,
            },
        )
        replace_doc(conn, old_id, pd)
        renamed += 1
    return renamed
