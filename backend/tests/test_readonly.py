"""The read-only proof: raw/ is byte-for-byte unchanged by any scan run."""

from __future__ import annotations

from tests.conftest import file_snapshot, run_scan, write_doc


def test_full_scan_does_not_touch_raw(corpus, settings, engine):
    before = file_snapshot(settings.raw_root)
    run_scan(engine, full=True)
    assert file_snapshot(settings.raw_root) == before


def test_incremental_scan_does_not_touch_raw(corpus, settings, engine):
    run_scan(engine, full=True)
    write_doc(settings, "notes/新增.md", "# 新增\n")
    before = file_snapshot(settings.raw_root)
    run_scan(engine)
    assert file_snapshot(settings.raw_root) == before


def test_scan_creates_no_auxiliary_files_under_raw(corpus, settings, engine):
    run_scan(engine, full=True)
    leftovers = {
        p.relative_to(settings.raw_root).as_posix()
        for p in settings.raw_root.rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    }
    # 快照里应该只有我们写入的语料（其 rel 集合等于语料键集合）
    assert leftovers == set((corpus).keys())
