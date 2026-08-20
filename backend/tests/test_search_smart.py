"""V0.5 智能检索：rerank 归一向、分级加分、matched_terms、smart snippet、mode 兼容。

使用自有小语料做确定性断言（标题/heading/短语/标签/path 加分可独立验证）。
"""

from __future__ import annotations

import pytest

from app.search.query import search
from tests.conftest import run_scan, write_doc

# 控制语料：每种加分场景独立成对
BOOST_DOCS = {
    "t/titlewin.md": "---\ntitle: 目标词\n---\n目标词 目标词 背景。\n",
    "t/bodyonly.md": "---\ntitle: 纯正文文档\n---\n目标词 目标词 背景。\n",
    "t/headding.md": "---\ntitle: 前标题甲\n---\n# 目标词\n\n目标词 目标词 背景。\n",
    "t/phrase2.md": "---\ntitle: 短语两处\n---\n精确合体 说明 精确合体 背景。\n",
    "t/phrase1.md": "---\ntitle: 短语一处\n---\n示例 精确合体 背景。\n",
    "t/phrase_none.md": "---\ntitle: 分散出现\n---\n精确 与 合体 分开出现 背景。\n",
    "t/tagging.md": "---\ntitle: 带标签\ntags: [财务核对]\n---\n财务核对 说明。\n",
    "t/nottag.md": "---\ntitle: 无标签\ntags: [其他]\n---\n财务核对 说明。\n",
    "t/正文文档.md": "---\ntitle: 纯正文\n---\n结算说明 内容。\n",
    "部署/结算说明备忘.md": "---\ntitle: 路径有词\n---\n结算说明 内容。\n",
    "t/bothwords.md": "---\ntitle: 双词命中\n---\n目标词 与 纯正文 同段出现，方便验证短语片段。\n",
}


@pytest.fixture()
def boostdocs(settings, engine):
    for rel, content in BOOST_DOCS.items():
        write_doc(settings, rel, content)
    run_scan(engine, full=True)


def _paths(result) -> list[str]:
    return [h.doc["rel_path"] for h in result.hits]


def test_smart_and_keyword_same_recall(engine, boostdocs):
    kw = search(engine, "目标词", mode="keyword")
    sm = search(engine, "目标词")  # 默认 smart
    assert kw.total == sm.total == 4
    assert set(_paths(kw)) == set(_paths(sm))


def test_title_boost_ranks_first(engine, boostdocs):
    paths = _paths(search(engine, "目标词"))
    # 标题命中(3.0) > heading(1.5) > 纯正文(0.4)
    assert paths[:3] == ["t/titlewin.md", "t/headding.md", "t/bodyonly.md"]


def test_headings_rank_above_body(engine, boostdocs):
    paths = _paths(search(engine, "目标词"))
    assert paths.index("t/headding.md") < paths.index("t/bodyonly.md")


def test_phrase_boost_and_recall(engine, boostdocs):
    res = search(engine, '"精确合体"')
    # 连续出现的两篇召回；分散出现的不召回（短语语义，不是 OR 分词）
    assert {p for p in _paths(res)} == {"t/phrase2.md", "t/phrase1.md"}
    # 频率更高的排前面（phrase 加分 2.0/次）
    assert _paths(res)[0] == "t/phrase2.md"


def test_tag_boost(engine, boostdocs):
    paths = _paths(search(engine, "财务核对"))
    assert paths.index("t/tagging.md") < paths.index("t/nottag.md")


def test_path_boost(engine, boostdocs):
    paths = _paths(search(engine, "结算说明"))
    assert paths.index("部署/结算说明备忘.md") < paths.index("t/正文文档.md")


def test_matched_terms_smart_only(engine, boostdocs):
    sm = search(engine, "目标词 纯正文")
    both = next(h for h in sm.hits if h.doc["rel_path"] == "t/bothwords.md")
    assert set(both.matched_terms) == {"纯正文", "目标词"}
    # AND 语义：缺任一词的文档不召回（titlewin 只有 目标词，无 纯正文）
    assert all(h.doc["rel_path"] != "t/titlewin.md" for h in sm.hits)

    kw = search(engine, "目标词 纯正文", mode="keyword")
    assert all(h.matched_terms == [] for h in kw.hits)


def test_snippet_covers_multiple_terms(engine, boostdocs):
    res = search(engine, "目标词 纯正文")
    hit = next(h for h in res.hits if h.doc["rel_path"] == "t/bothwords.md")
    joined = " ".join(s.text for s in hit.snippets)
    assert "目标词" in joined and "纯正文" in joined
    assert any("<mark>" in s.text for s in hit.snippets)  # REST/UI 保留高亮


def test_scores_desc_and_non_negative(engine, boostdocs):
    scores = [h.score for h in search(engine, "目标词").hits]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= 0 for s in scores)


def test_keyword_score_is_raw_bm25(engine, boostdocs):
    kw = search(engine, "目标词", mode="keyword")
    sm = search(engine, "目标词")
    # keyword 保持原始 bm25（越小越相关、可能为负）；smart 已归一化（≥0 越大越相关）
    assert kw.hits[0].score != sm.hits[0].score
    assert sm.hits[0].score > 0


def test_total_independent_of_offset(engine, boostdocs):
    total = search(engine, "目标词").total
    assert search(engine, "目标词", offset=999).hits == []
    assert search(engine, "目标词", offset=999).total == total


def test_special_chars_still_safe(engine, boostdocs):
    assert search(engine, '(((( ').total == 0
    assert search(engine, 'a"b').total == 0
