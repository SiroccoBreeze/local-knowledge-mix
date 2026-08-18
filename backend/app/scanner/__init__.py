"""Metadata => index reconciliation ("snapshot diff").

run_scan() compares the raw/ filesystem to the documents table and updates
every derived artifact in one SQLite transaction:

- Phase A (pure reads, no open transaction): walk raw/, hash + parse every
  in-scope file, keep only the diff.
- Phase B (single write transaction): upsert metadata, rebuild the contentless
  FTS rows that changed, mark whatever vanished as 'missing', detect renames
  (content-hash matching, doc id preserved), resolve and insert links, write
  the report.

The scanner is strictly read-only with respect to raw/: nothing in this module
opens a file for writing.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, Engine, text

from app.config import get_settings
from app.db import schema as db_schema
from app.db.engine import get_engine
from app.scanner import index as db_index
from app.scanner.parse import ParsedDoc, parse_markdown
from app.scanner.walk import FileInfo, walk_files


@dataclass
class ScanReport:
    started_at: str
    finished_at: str
    duration_ms: int
    raw_root: str
    full: bool
    total_docs: int = 0
    added: int = 0
    changed: int = 0
    unchanged: int = 0
    skipped: int = 0
    missing: int = 0
    failed: int = 0


@dataclass
class _Work:
    fi: FileInfo
    sha: str
    pd: ParsedDoc
    prev: dict | None


@dataclass
class _Failure:
    fi: FileInfo
    prev: dict | None
    error: str


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def run_scan(engine: Engine | None = None, *, full: bool = False) -> ScanReport:
    engine = engine or get_engine()
    raw_root = get_settings().raw_root.resolve()
    started = time.monotonic()
    started_iso = now_iso()
    ended_iso = now_iso()

    # Schema must exist before the read phase touches documents (idempotent,
    # near-zero cost on an existing db).
    with engine.begin() as schema_conn:
        db_schema.ensure_schema(schema_conn)

    work, failures, unchanged, skipped, seen = _read_phase(engine, raw_root, full)

    with engine.begin() as conn:
        db_schema.ensure_schema(conn)
        if full:  # rebuild the whole FTS index (contentless: recreate the table)
            db_schema.drop_fts(conn)
            db_schema.create_fts(conn)

        added = 0
        changed = 0
        added_files: dict[str, tuple[FileInfo, ParsedDoc]] = {}
        pending_links: list[tuple[int, str, str, str]] = []  # (doc_id, src_rel, kind, target)

        for item in work:
            doc_id = db_index.insert_doc(
                conn,
                item.fi,
                item.sha,
                item.pd,
                ended_iso,
                doc_id=item.prev["id"] if item.prev else None,
            )
            if item.prev is not None:
                changed += 1
            else:
                added += 1
                added_files.setdefault(item.sha, (item.fi, item.pd))
            pending_links.extend(
                (doc_id, item.fi.rel_path, kind, target) for kind, target in item.pd.links
            )

        # Failed files are recorded (never crash the whole scan).
        for case in failures:
            db_index.mark_failed(conn, case.fi, case.prev, case.error, ended_iso)

        # Files that vanished since the last scan.
        db_index.mark_missing(conn, seen, ended_iso)

        # Links first: detect_renames() rewires from_doc/to_doc rows that point
        # at a merged-away id, so links inserted now get redirected too.
        maps = db_index.link_maps(conn)
        db_index.insert_links(conn, pending_links, maps)

        # content-preserving moves: keep the old rowid + links.
        renames = db_index.detect_renames(conn, added_files, ended_iso)
        added = max(0, added - renames)
        changed += renames

        report = ScanReport(
            started_at=started_iso,
            finished_at=ended_iso,
            duration_ms=int((time.monotonic() - started) * 1000),
            raw_root=str(raw_root),
            full=full,
            added=added,
            changed=changed,
            unchanged=unchanged,
            skipped=skipped,
            failed=len(failures),
            missing=_count(conn, "SELECT count(*) FROM documents WHERE status='missing'"),
            total_docs=_count(conn, "SELECT count(*) FROM documents"),
        )

        conn.execute(
            text("UPDATE documents SET last_seen = :now WHERE status = 'indexed'"), {"now": ended_iso}
        )
        db_schema.set_meta(conn, "schema_version", str(get_settings().schema_version))
        db_schema.set_meta(conn, "last_scan_at", ended_iso)
        db_schema.set_meta(conn, "last_scan_report", json.dumps(asdict(report), ensure_ascii=False))

    return report


def _read_phase(
    engine: Engine, raw_root, full: bool
) -> tuple[list[_Work], list[_Failure], int, int, set[str]]:
    """Walk, hash, parse — pure reads. Returns the diff plan for phase B."""
    with engine.connect() as conn:
        existing = {
            row["rel_path"]: row
            for row in conn.execute(
                text("SELECT id, rel_path, sha256, mtime_ns, size, status FROM documents")
            ).mappings()
        }

    work: list[_Work] = []
    failures: list[_Failure] = []
    unchanged = skipped = 0
    seen: set[str] = set()

    for fi in walk_files(raw_root):
        seen.add(fi.rel_path)
        prev = existing.get(fi.rel_path)
        if (
            prev
            and not full
            and prev["status"] != "failed"
            and prev["mtime_ns"] == fi.mtime_ns
            and prev["size"] == fi.size
        ):
            unchanged += 1
            continue
        if fi.size > get_settings().max_file_bytes:
            skipped += 1
            failures.append(_Failure(fi=fi, prev=prev, error="文件超大，超过上限"))
            continue
        try:
            data = fi.abs_path.read_bytes()
        except OSError as exc:
            failures.append(_Failure(fi=fi, prev=prev, error=f"读取失败: {exc}"))
            continue
        sha = hashlib.sha256(data).hexdigest()
        if prev and not full and prev["sha256"] == sha:
            unchanged += 1
            continue
        try:
            pd = parse_markdown(data.decode("utf-8", errors="replace"), fi.rel_path)
        except Exception as exc:  # noqa: BLE001 — one bad file must never abort a scan
            failures.append(_Failure(fi=fi, prev=prev, error=f"解析失败: {exc}"))
            continue
        work.append(_Work(fi=fi, sha=sha, pd=pd, prev=prev))

    return work, failures, unchanged, skipped, seen


def _count(conn: Connection, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar())


__all__ = ["ScanReport", "run_scan"]
