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

    work, failures, unchanged, skipped, seen, asset_candidates = _read_phase(
        engine, raw_root, full
    )

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

        # Assets: renames may have re-assigned ids, so read the final id map.
        # Runs even when every document took the fast path (stale assets).
        if seen:
            rows = conn.execute(
                text(
                    "SELECT id, rel_path FROM documents WHERE rel_path IN"
                    " (SELECT value FROM json_each(:rels))"
                ),
                {"rels": json.dumps(sorted(seen), ensure_ascii=False)},
            ).mappings()
            doc_id_by_rel = {row["rel_path"]: row["id"] for row in rows}
            # 仅修剪"本次确认过引用集合"的文档（解析成功 ⇒ 有候选；失败文档不碰）
            parsed_docs = {c.doc_rel for c in asset_candidates}
            db_index.upsert_assets(conn, doc_id_by_rel, asset_candidates, parsed_docs, ended_iso)

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
) -> tuple[list[_Work], list[_Failure], int, int, set[str], list[object]]:
    """Walk, hash, parse — pure reads (raw/ 严格只读)

    Returns the diff plan for phase B plus resolved asset candidates.
    """
    with engine.connect() as conn:
        existing = {
            row["rel_path"]: row
            for row in conn.execute(
                text("SELECT id, rel_path, sha256, mtime_ns, size, status FROM documents")
            ).mappings()
        }
        existing_assets = {
            (row["doc_rel"], row["relative_path"]): row
            for row in conn.execute(
                text(
                    "SELECT a.relative_path, a.sha256, a.mtime_ns, a.size, a.status,"
                    " d.rel_path AS doc_rel FROM assets a"
                    " JOIN documents d ON d.id = a.document_id"
                )
            ).mappings()
        }

    work: list[_Work] = []
    failures: list[_Failure] = []
    unchanged = skipped = 0
    seen: set[str] = set()
    asset_candidates: list[db_index.AssetCandidate] = []

    # 每篇文档的已解析引用（快速通道文档复用库中关联，避免重解析）
    assets_by_doc_final: dict[str, list[str]] = {}
    for a_row in existing_assets.values():
        assets_by_doc_final.setdefault(a_row["doc_rel"], []).append(a_row["relative_path"])

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
            asset_candidates.extend(
                _candidates_from_refs(
                    raw_root, fi.rel_path, assets_by_doc_final.get(fi.rel_path, []), existing_assets
                )
            )
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
            asset_candidates.extend(
                _candidates_from_refs(
                    raw_root, fi.rel_path, assets_by_doc_final.get(fi.rel_path, []), existing_assets
                )
            )
            continue
        try:
            pd = parse_markdown(data.decode("utf-8", errors="replace"), fi.rel_path)
        except Exception as exc:  # noqa: BLE001 — one bad file must never abort a scan
            failures.append(_Failure(fi=fi, prev=prev, error=f"解析失败: {exc}"))
            continue
        work.append(_Work(fi=fi, sha=sha, pd=pd, prev=prev))
        refs = [
            db_index.resolve_asset_path(fi.rel_path, ref)
            for ref in pd.asset_refs
            if db_index.resolve_asset_path(fi.rel_path, ref) is not None
        ]
        asset_candidates.extend(
            _candidates_from_refs(raw_root, fi.rel_path, refs, existing_assets)
        )

    return work, failures, unchanged, skipped, seen, asset_candidates


def _candidates_from_refs(raw_root, doc_rel: str, refs: list[str], existing_assets) -> list[object]:
    """Stat/hash each referenced path (fast path: reuse stored hash/size/mtime)."""
    out: list[db_index.AssetCandidate] = []
    seen_paths: set[str] = set()
    for asset_rel in refs:
        if asset_rel in seen_paths:
            continue
        seen_paths.add(asset_rel)
        try:
            st = (raw_root / asset_rel).stat()
        except OSError:
            out.append(db_index.AssetCandidate(doc_rel, asset_rel, False, 0, 0, ""))
            continue
        prev = existing_assets.get((doc_rel, asset_rel))
        if (
            prev
            and prev["status"] != "missing"
            and prev["size"] == st.st_size
            and prev["mtime_ns"] == st.st_mtime_ns
        ):
            sha = prev["sha256"]
        else:
            try:
                sha = hashlib.sha256((raw_root / asset_rel).read_bytes()).hexdigest()
            except OSError:
                out.append(db_index.AssetCandidate(doc_rel, asset_rel, False, 0, 0, ""))
                continue
        out.append(db_index.AssetCandidate(doc_rel, asset_rel, True, st.st_size, st.st_mtime_ns, sha))
    return out


def _count(conn: Connection, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar())


__all__ = ["ScanReport", "run_scan"]
