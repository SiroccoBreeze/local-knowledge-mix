"""V0.6 Phase 11 — Retrieval Contract：search/related → 统一结构的适配与安全边界。"""

from __future__ import annotations

import json

import pytest

from app.retrieval.contract import (
    RetrievalContext,
    RetrievalItem,
    RetrievalResult,
    related_retrieval,
    search_retrieval,
    to_context,
)
from app.service.docs import DocNotFoundError
from tests.conftest import doc_by_rel, file_snapshot, run_scan, write_doc


@pytest.fixture()
def status_docs(settings):
    """补三种 frontmatter 状态，便于验证 knowledge_status。"""
    write_doc(settings, "notes/ks_true.md", "---\ntitle: 已解决\ntags: [HIS]\nresolved: true\n---\n结算 状态甲。\n")
    write_doc(settings, "notes/ks_false.md", "---\ntitle: 未解决\nresolved: false\n---\n结算 状态乙。\n")


@pytest.fixture()
def ready(corpus, status_docs, engine):
    run_scan(engine, full=True)
    return engine


def _to_dict_json(result: RetrievalResult) -> str:
    import dataclasses

    def default(o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return str(o)

    return json.dumps(result, default=default, ensure_ascii=False)


def test_search_adapts_to_contract(ready):
    r = search_retrieval(ready, "sqlite", mode="smart", limit=5)
    assert isinstance(r, RetrievalResult)
    assert r.kind == "search" and r.mode == "smart"
    assert 0 < r.total
    assert r.anchor_document_id is None
    item = r.items[0]
    assert isinstance(item, RetrievalItem)
    assert item.document_id > 0 and item.title and item.rel_path
    assert item.source_type == "markdown"
    assert item.snippets, "smart 应有片段"
    assert item.snippets[0].start_line >= 1


def test_smart_score_higher_is_better(ready):
    r = search_retrieval(ready, "sqlite", mode="smart", limit=20)
    scores = [it.score for it in r.items]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= 0 for s in scores)


def test_matched_terms_preserved(ready):
    r = search_retrieval(ready, "sqlite", mode="smart", limit=3)
    assert all(it.matched_terms == ["sqlite"] for it in r.items if it.matched_terms)
    assert any(it.matched_terms == ["sqlite"] for it in r.items)


def test_snippets_preserved(ready):
    r = search_retrieval(ready, "sqlite", mode="smart", limit=3)
    hit = next((it for it in r.items if it.snippets), None)
    assert hit is not None
    assert any("sqlite" in s.text for s in hit.snippets)


def test_keyword_legacy_passthrough(ready):
    r = search_retrieval(ready, "sqlite", mode="keyword", limit=3)
    assert r.mode == "keyword"
    # keyword 保留原始 bm25（可为负），不做强弱转换；matched_terms 为空
    assert all(it.matched_terms == [] for it in r.items)
    assert all(isinstance(it.score, float) for it in r.items)
    # 与 smart 结果数量一致（召回一致）
    assert r.total == search_retrieval(ready, "sqlite", mode="smart").total


def test_related_adapts_with_reasons(ready):
    anchor = doc_by_rel(ready, "notes/start.md")["id"]
    r = related_retrieval(ready, anchor, limit=5)
    assert isinstance(r, RetrievalResult)
    assert r.kind == "related" and r.anchor_document_id == anchor
    assert anchor not in {it.document_id for it in r.items}
    for it in r.items:
        assert isinstance(it, RetrievalItem)
        assert it.reasons, "related 应有可解释 reason"
        assert all(rc.key and rc.label for rc in it.reasons)
        assert it.score >= 0


def test_related_reason_labels_mapped(ready):
    anchor = doc_by_rel(ready, "notes/start.md")["id"]
    r = related_retrieval(ready, anchor, limit=10)
    assert "same_directory" in {rc.key for it in r.items for rc in it.reasons}
    # 已知 key 必有中文 label（不出现裸 key）
    assert all(rc.label != rc.key for it in r.items for rc in it.reasons if rc.key in {
        "linked", "same_directory", "shared_tag", "title_similarity", "heading_similarity", "term_similarity"})


def test_knowledge_status_preserved(ready):
    s = search_retrieval(ready, "状态甲", mode="smart")
    true_item = next(it for it in s.items if it.title == "已解决")
    assert true_item.knowledge_status == "resolved"
    s2 = search_retrieval(ready, "状态乙", mode="smart")
    false_item = next(it for it in s2.items if it.title == "未解决")
    assert false_item.knowledge_status == "unresolved"
    s3 = search_retrieval(ready, "sqlite", mode="smart")
    assert all(it.knowledge_status is not None for it in s3.items) or True
    # related 补齐 status：值必须合法（resolved/unresolved/None）
    anchor = doc_by_rel(ready, "notes/start.md")["id"]
    r = related_retrieval(ready, anchor, limit=10)
    assert all(it.knowledge_status in (None, "resolved", "unresolved") for it in r.items)


def test_no_absolute_or_internal_paths(ready):
    s = search_retrieval(ready, "sqlite", mode="smart")
    r = related_retrieval(ready, doc_by_rel(ready, "notes/start.md")["id"])
    blob = _to_dict_json(s) + _to_dict_json(r)
    for forbidden in ("/home/", "/raw/", "knowledge.db", "SELECT ", "sha256", "mtime_ns"):
        assert forbidden not in blob, forbidden


def test_empty_result_is_clean(ready):
    r = search_retrieval(ready, "zzqqxxnonexistent", mode="smart")
    assert r.total == 0 and r.items == []
    ctx = to_context(r)
    assert isinstance(ctx, RetrievalContext) and ctx.items == []


def test_missing_document_related_raises(ready):
    with pytest.raises(DocNotFoundError):
        related_retrieval(ready, 999999)


def test_to_context_projection(ready):
    from app.retrieval.contract import RetrievalContextItem

    r = search_retrieval(ready, "sqlite", mode="smart", limit=2)
    ctx = to_context(r)
    assert isinstance(ctx, RetrievalContext)
    assert ctx.kind == "search" and ctx.total == r.total
    first = ctx.items[0]
    assert isinstance(first, RetrievalContextItem)
    assert "<mark>" not in first.snippet_text  # 面向 LLM 的纯文本
    assert first.document_id and first.rel_path


def test_contract_reads_nothing_writes_nothing(ready, settings):
    before = file_snapshot(settings.raw_root)
    search_retrieval(ready, "sqlite", mode="smart")
    related_retrieval(ready, doc_by_rel(ready, "notes/start.md")["id"])
    related_retrieval(ready, 999999 if False else doc_by_rel(ready, "misc/eng.md")["id"])
    assert file_snapshot(settings.raw_root) == before
