"""Search behavior: trigram CJK, english, phrase, exclude, LIKE fallback."""

from __future__ import annotations

from tests.conftest import run_scan, search


def _paths(result) -> set[str]:
    return {h.doc["rel_path"] for h in result.hits}


def test_english_word(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "sqlite")
    assert res.total == 2  # misc/eng.md + misc/rejected.md
    assert _paths(res) == {"misc/eng.md", "misc/rejected.md"}


def test_cjk_body_token(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "知识库系统")
    assert {"notes/start.md", "notes/中文笔记.md"} <= _paths(res)


def test_cjk_three_char_substring(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "知识库")
    assert "notes/start.md" in _paths(res)


def test_cjk_title_only(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "深度中")
    assert _paths(res) == {"notes/中文笔记.md"}


def test_code_block_content_searchable(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "hello")
    assert _paths(res) == {"notes/start.md"}
    assert any("hello" in s.text for s in res.hits[0].snippets)


def test_phrase_query(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, '"exact phrase"')
    assert _paths(res) == {"notes/snippet_hunt.md"}
    assert any("<mark>" in s.text and "exact" in s.text for s in res.hits[0].snippets)


def test_exclude_term(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "sqlite -排除词")
    assert _paths(res) == {"misc/eng.md"}


def test_two_char_term_via_like_fallback(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "AI")
    assert _paths(res) == {"notes/ai.md"}  # 命中标题列（text 存于 DB）


def test_no_match(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "zzqqxx")
    assert res.total == 0
    assert res.hits == []


def test_empty_query_library_returns_empty(corpus, engine):
    run_scan(engine, full=True)
    res = search(engine, "---")
    assert res.total == 0


def test_pagination(corpus, engine):
    run_scan(engine, full=True)
    page1 = search(engine, "sqlite", limit=1, offset=0)
    page2 = search(engine, "sqlite", limit=1, offset=1)
    assert page1.total == 2
    assert len(page1.hits) == 1 and len(page2.hits) == 1
    assert page1.hits[0].doc["rel_path"] != page2.hits[0].doc["rel_path"]


def test_snippet_line_numbers(corpus, engine):
    run_scan(engine, full=True)
    hit = search(engine, "sqlite").hits[0]
    assert len(hit.snippets) >= 1
    snip = hit.snippets[0]
    assert snip.start_line >= 1
    assert snip.end_line >= snip.start_line


def test_junk_terms_are_scrubbed_not_fatal(corpus, engine):
    run_scan(engine, full=True)
    # 括号/星号/引号等特殊字符已被清洗，不应该让查询 500
    assert search(engine, 'sqlite (**))').total == 2
    assert search(engine, 'a"b').total == 0  # 引号被清洗，剩两字符词，无标题命中
