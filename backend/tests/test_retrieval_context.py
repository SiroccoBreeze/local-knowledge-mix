"""V0.6 Phase 12 — Context Builder: retrieval results -> safe plain-text context."""

from __future__ import annotations

from app.retrieval.context import (
    build_context,
    merge_contexts,
)
from app.retrieval.contract import (
    RetrievalItem,
    RetrievalResult,
    related_retrieval,
    search_retrieval,
)
from app.search.query import Snippet
from tests.conftest import doc_by_rel, file_snapshot, run_scan, write_doc


def _dangerous_result():
    """含绝对路径 /raw/ /home/ knowledge.db SQL HTML 的对抗测试."""
    items = [
        RetrievalItem(
            document_id=1, title="危险的文档", rel_path="notes/danger.md",
            score=0.8, snippets=[Snippet(text=(
                "路径泄漏：/home/ub/WorkerSP/data/knowledge.db 和 /raw/notes/test.md "
                "以及 <mark>结算</mark> <script>alert(1)</script> "
                "SELECT * FROM documents 都是敏感信息"
            ), start_line=1, end_line=2)],
            knowledge_status=None,
        ),
        RetrievalItem(
            document_id=2, title="安全文档", rel_path="notes/safe.md",
            score=0.6, snippets=[Snippet(text="正常内容。", start_line=1, end_line=1)],
            knowledge_status="resolved",
        ),
    ]
    return RetrievalResult(
        kind="search", mode="smart", query=None, anchor_document_id=None,
        total=2, items=items, limit=10, offset=0,
    )


def test_search_to_context(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=2)
    ctx = build_context(result)
    assert isinstance(ctx, str) and len(ctx) > 0
    assert "[1]" in ctx and "路径：" in ctx and "相关度：" in ctx


def test_related_to_context(corpus, engine):
    run_scan(engine, full=True)
    anchor = doc_by_rel(engine, "notes/start.md")["id"]
    result = related_retrieval(engine, anchor, limit=3)
    ctx = build_context(result)
    assert isinstance(ctx, str) and len(ctx) > 0
    assert "[1]" in ctx


def test_single_document_context(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=1)
    ctx = build_context(result)
    assert "[1]" in ctx and "[2]" not in ctx


def test_multi_document_context(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=3)
    ctx = build_context(result)
    assert 1 <= ctx.count("[") <= 3


def test_merge_dedup(corpus, engine):
    run_scan(engine, full=True)
    sr = search_retrieval(engine, "sqlite", mode="smart", limit=3)
    anchor = doc_by_rel(engine, "notes/start.md")["id"]
    rr = related_retrieval(engine, anchor, limit=3)
    merged = merge_contexts([sr, rr])
    assert isinstance(merged, str) and len(merged) > 0
    seen = set()
    for line in merged.split("\n"):
        if line.startswith("路径："):
            p = line[3:]
            assert p not in seen, f"duplicate: {p}"
            seen.add(p)


def test_max_documents_limit(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=20)
    ctx = build_context(result, max_docs=1)
    assert ctx.count("[") == 1


def test_max_context_chars_limit(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=5)
    ctx = build_context(result, max_chars=100)
    assert len(ctx) <= 250


def test_max_snippet_chars_limit(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=1)
    ctx = build_context(result, max_snippet=10)
    assert len(ctx) < 300


def test_deterministic_truncation(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=5)
    a = build_context(result, max_chars=200)
    b = build_context(result, max_chars=200)
    assert a == b


def test_empty_result(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "zzqqxxnonexistent", mode="smart")
    ctx = build_context(result)
    assert ctx == ""


def test_smart_score_preserved(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=1)
    ctx = build_context(result)
    assert "相关度：" in ctx


def test_keyword_legacy_score_unchanged(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="keyword", limit=1)
    ctx = build_context(result)
    assert "相关度：" in ctx


def test_snippet_content_present(corpus, engine):
    run_scan(engine, full=True)
    result = search_retrieval(engine, "sqlite", mode="smart", limit=2)
    ctx = build_context(result)
    assert "sqlite" in ctx.lower()


def test_knowledge_status_preserved(corpus, settings, engine):
    write_doc(settings, "notes/ks_true.md",
              "---\ntitle: 已解决\ntags: [HIS]\nresolved: true\n---\n结算 状态甲。\n")
    run_scan(engine, full=True)
    result = search_retrieval(engine, "状态甲", mode="smart", limit=1)
    ctx = build_context(result)
    if "已解决" in ctx:
        assert "已解决" in ctx
    elif "状态：" in ctx:
        assert "状态：" in ctx


def test_mark_stripped():
    r = _dangerous_result()
    ctx = build_context(r)
    assert "<mark>" not in ctx


def test_html_script_sanitized(corpus, engine):
    run_scan(engine, full=True)
    r = _dangerous_result()
    ctx = build_context(r)
    assert "<mark>" not in ctx
    assert "<script>" not in ctx
    assert "alert(" not in ctx
    assert "SELECT * FROM documents" not in ctx


def test_absolute_path_not_leaked():
    r = _dangerous_result()
    ctx = build_context(r)
    assert "/home/" not in ctx
    assert "/raw/" not in ctx
    assert "knowledge.db" not in ctx
    assert "SELECT * FROM" not in ctx


def test_no_internal_path_or_db_leak():
    items = [RetrievalItem(
        document_id=99, title="敏感测试", rel_path="notes/secret.md",
        score=0.5, snippets=[Snippet(text=(
            "/home/user/knowledge.db /raw/notes/test.md /Users/admin/data.db"
        ), start_line=1, end_line=1)],
    )]
    r = RetrievalResult(kind="search", mode="smart", query=None, anchor_document_id=None,
                        total=1, items=items, limit=10, offset=0)
    ctx = build_context(r)
    assert "/home/" not in ctx
    assert "/raw/" not in ctx
    assert "knowledge.db" not in ctx
    assert "/Users/" not in ctx


def test_reads_nothing_writes_nothing(corpus, settings, engine):
    run_scan(engine, full=True)
    before = file_snapshot(settings.raw_root)
    sr = search_retrieval(engine, "sqlite", mode="smart", limit=2)
    rr = related_retrieval(engine, doc_by_rel(engine, "notes/start.md")["id"], limit=2)
    build_context(sr)
    build_context(rr)
    merge_contexts([sr, rr])
    assert file_snapshot(settings.raw_root) == before


def test_deterministic(corpus, engine):
    run_scan(engine, full=True)
    sr = search_retrieval(engine, "sqlite", mode="smart", limit=3)
    rr = related_retrieval(engine, doc_by_rel(engine, "notes/start.md")["id"], limit=2)
    assert build_context(sr) == build_context(sr)
    assert merge_contexts([sr, rr]) == merge_contexts([sr, rr])


def test_adversarial_security():
    items = [RetrievalItem(
        document_id=1, title="漏洞测试", rel_path="notes/泄漏.md",
        score=0.9, snippets=[Snippet(text=(
            "服务器路径：/home/ub/WorkerSP/data/knowledge.db-wal "
            "raw路径：/raw/notes/test.md "
            "SQL注入：SELECT * FROM documents WHERE 1=1 "
            "HTML：<mark>高亮</mark> <script>alert('xss')</script> "
            "INSERT INTO assets VALUES(1,2,3) "
            "DELETE FROM documents WHERE 1=1"
        ), start_line=1, end_line=2)],
    )]
    r = RetrievalResult(kind="search", mode="smart", query=None, anchor_document_id=None,
                        total=1, items=items, limit=10, offset=0)
    ctx = build_context(r)
    for forbidden in (
        "/home/", "/raw/", "knowledge.db", "SELECT * FROM",
        "<mark>", "<script>", "alert(",
        "INSERT INTO", "DELETE FROM",
    ):
        assert forbidden not in ctx, f"leak: {forbidden}"
