"""Rebuildability: deleting data/knowledge.db + --full reproduces everything."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db.engine import get_engine
from app.db.schema import ensure_schema
from tests.conftest import run_scan, search


def _id_set(engine) -> set[int]:
    with engine.connect() as conn:
        return {row[0] for row in conn.execute(text("SELECT id FROM documents"))}


def _hit_paths(engine, q: str) -> set[str]:
    return {h.doc["rel_path"] for h in search(engine, q).hits}


def test_rebuild_after_deleting_db(corpus, settings, engine):
    run_scan(engine, full=True)
    ids_before = _id_set(engine)
    links_before = _hit_paths(engine, "知识库")
    assert ids_before and links_before  # 语料真的索引上了

    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(str(settings.db_path) + suffix).unlink(missing_ok=True)

    fresh = get_engine()
    # 模拟恢复流程：schema 自动重建 + 全量扫描
    with fresh.begin() as conn:
        ensure_schema(conn)
    report = run_scan(fresh, full=True)
    assert report.added == report.total_docs
    assert _id_set(fresh) == ids_before
    assert _hit_paths(fresh, "知识库") == links_before

    # contentless 恢复后原文仍然逐字节来自磁盘
    with fresh.connect() as conn:
        row = conn.execute(
            text("SELECT rel_path FROM documents WHERE rel_path='notes/start.md'")
        ).first()
    assert row is not None
    on_disk = (settings.raw_root / row[0]).read_bytes()
    assert on_disk.startswith(b"---")
    fresh.dispose()
