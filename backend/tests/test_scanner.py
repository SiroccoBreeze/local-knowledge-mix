"""Scanner reconciliation: first scan, idempotence, add/modify/delete, rename."""

from __future__ import annotations

from sqlalchemy import text

from tests.conftest import CORPUS, doc_by_rel, run_scan, search, write_bytes, write_doc

N_DOCS = len(CORPUS)


def test_first_full_scan(corpus, engine):
    r = run_scan(engine, full=True)
    assert r.added == N_DOCS
    assert r.unchanged == 0
    assert r.changed == 0
    assert r.failed == 0
    assert r.missing == 0
    assert r.total_docs == N_DOCS


def test_rescan_is_idempotent(corpus, engine):
    run_scan(engine, full=True)
    r = run_scan(engine)
    assert r.added == 0
    assert r.changed == 0
    assert r.unchanged == N_DOCS
    assert r.missing == 0
    assert r.failed == 0


def test_add_modify_delete(corpus, settings, engine):
    run_scan(engine, full=True)

    write_doc(settings, "notes/new.md", "# 新文档\n内容新增触发。\n")
    _append(settings, "notes/snippet_hunt.md", "\n改动后新增关键词表面测试。\n")
    (settings.raw_root / "deep/link_target.md").unlink()

    r = run_scan(engine)
    assert r.added == 1
    assert r.changed == 1
    assert r.missing == 1
    assert r.total_docs == N_DOCS + 1  # 删掉的文档行保留（审计）

    assert doc_by_rel(engine, "notes/new.md")["status"] == "indexed"
    assert doc_by_rel(engine, "notes/snippet_hunt.md")["status"] == "indexed"
    assert doc_by_rel(engine, "deep/link_target.md")["status"] == "missing"

    # 新增内容可检索；missing 文档不再命中
    assert {h.doc["rel_path"] for h in search(engine, "新增触发").hits} == {"notes/new.md"}
    assert search(engine, "关键词表面").total == 1
    assert search(engine, "被链接的目标文档").total == 0


def test_modified_doc_hash_updates(corpus, settings, engine):
    run_scan(engine, full=True)
    before = doc_by_rel(engine, "notes/special.md")["sha256"]
    write_doc(settings, "notes/special.md", "改动之后全文变化。\n")
    run_scan(engine)
    after = doc_by_rel(engine, "notes/special.md")["sha256"]
    assert before != after
    assert search(engine, "全文变化").total == 1


def test_rename_preserves_doc_id(corpus, settings, engine):
    run_scan(engine, full=True)
    old = doc_by_rel(engine, "notes/start.md")
    assert old is not None
    old_id = old["id"]

    (settings.raw_root / "notes" / "start.md").rename(settings.raw_root / "notes" / "start2.md")
    r = run_scan(engine)
    # 内容相同的移动 = 非新增、非缺失：id 被保留下来
    assert r.added == 0
    assert r.changed == 1
    assert r.missing == 0

    moved = doc_by_rel(engine, "notes/start2.md")
    assert moved["id"] == old_id
    assert doc_by_rel(engine, "notes/start.md") is None
    assert "notes/start2.md" in {h.doc["rel_path"] for h in search(engine, "知识库").hits}


def test_rename_redirects_fresh_links_to_kept_id(corpus, settings, engine):
    """一个文件链接到改名后的新路径：扫描重命名后，链接应指向保留的旧 id。"""
    run_scan(engine, full=True)
    eng_id = doc_by_rel(engine, "misc/eng.md")["id"]

    write_doc(settings, "deep/notes_today.md", "今天读到了 [英文页](../misc/english.md)。\n")
    (settings.raw_root / "misc" / "eng.md").rename(settings.raw_root / "misc" / "english.md")
    run_scan(engine)

    assert doc_by_rel(engine, "misc/english.md")["id"] == eng_id
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT l.to_doc FROM links l"
                " JOIN documents d ON d.id = l.from_doc"
                " WHERE d.rel_path='deep/notes_today.md' AND l.target='../misc/english.md'"
            )
        ).first()
    assert row is not None and row[0] == eng_id


def test_broken_frontmatter_is_indexed(corpus, engine):
    run_scan(engine, full=True)
    broken = doc_by_rel(engine, "notes/frontmatter_broken.md")
    assert broken["status"] == "indexed"
    assert broken["scan_error"] is not None and "frontmatter" in broken["scan_error"]
    assert broken["title"] == "frontmatter_broken"  # 兜底：文件名
    assert search(engine, "正文还能用").total == 1  # 内容仍可检索


def test_non_markdown_and_hidden_ignored(corpus, settings, engine):
    write_bytes(settings, "assets/logo.png", b"\x89PNG\r\n\x1a\n")
    write_doc(settings, "notes/.hidden.md", "# 隐藏\n")
    assert run_scan(engine, full=True).total_docs == N_DOCS  # png 与 .hidden.md 都不入库

    write_doc(settings, "notes/UPPER.MD", "# 大写扩展名\n")
    assert run_scan(engine).added == 1  # 大小写不敏感的扩展名过滤


def test_oversized_file_recorded_not_crashing(corpus, settings, engine):
    settings.max_file_bytes = 8
    write_doc(settings, "notes/too_big.md", "超过八字节上限的文档内容。\n")
    r = run_scan(engine, full=True)
    # 语料中唯一 ≤8 字节的文件是空的 empty.md（0 字节），其余全部超限跳过
    assert r.failed == len(CORPUS)  # 14 篇语料 + too_big.md
    assert r.skipped == len(CORPUS)
    assert r.added == 1  # empty.md
    assert r.total_docs == len(CORPUS) + 1
    assert doc_by_rel(engine, "notes/too_big.md")["status"] == "failed"


def _append(settings, rel: str, content: str) -> None:
    with (settings.raw_root / rel).open("a", encoding="utf-8") as fh:
        fh.write(content)
