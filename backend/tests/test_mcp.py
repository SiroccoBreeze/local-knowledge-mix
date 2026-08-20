"""MCP tools: read-only knowledge access over the existing engine/search."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.mcp.server import make_server
from app.service.files import raw_path_for, read_raw_bytes
from tests.conftest import CORPUS, doc_by_rel, file_snapshot, run_scan, write_bytes, write_doc

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" + b"\xff" * 16
PDF = b"%PDF-1.4 fake pdf bytes\n"


@pytest.fixture()
def assets(settings):
    """附加资产文件 + 引用它们的文档。"""
    write_bytes(settings, "assets/logo.png", PNG)
    write_bytes(settings, "files/report.pdf", PDF)
    write_doc(
        settings,
        "notes/uses.md",
        "# 引用\n\n![图](../assets/logo.png) 与 [附件](../files/report.pdf)\n",
    )


@pytest.fixture()
def mcp(corpus, engine, assets):
    run_scan(engine, full=True)
    return make_server(engine)


@pytest.fixture()
def knowledge(settings):
    """三种 frontmatter 状态的可验证文档。"""
    write_doc(settings, "notes/know_true.md", "---\ntitle: 已解决的知识\ntags: [HIS]\nresolved: true\n---\n内容甲。\n")
    write_doc(settings, "notes/know_false.md", "---\ntitle: 未解决的知识\nresolved: false\n---\n内容乙。\n")
    write_doc(settings, "notes/know_state.md", "---\ntitle: 带状态的知识\nstatus: deprecated\n---\n内容丙。\n")
    write_doc(settings, "notes/know_none.md", "---\ntitle: 无状态的知识\n---\n内容丁。\n")


def call(server, name: str, args: dict) -> tuple[dict | list | str, bool]:
    """调用 FastMCP 工具：成功返回 (解析结果, False)；抛错返回 (错误信息, True)。"""
    try:
        contents = asyncio.run(server.call_tool(name, args))
    except Exception as exc:  # noqa: BLE001 — mcp 1.x 工具错误以异常形式暴露
        return str(exc), True
    if not contents:
        return None, False
    text = contents[0].text if hasattr(contents[0], "text") else str(contents[0])
    try:
        return json.loads(text), False
    except json.JSONDecodeError:
        return text, False


def doc_id(engine, rel: str) -> int:
    return doc_by_rel(engine, rel)["id"]


def test_registers_seven_tools(mcp):
    names = sorted(t.name for t in asyncio.run(mcp.list_tools()))
    assert names == [
        "find_related_documents",
        "get_document",
        "get_document_assets",
        "get_document_links",
        "get_knowledge_stats",
        "list_documents",
        "search_documents",
    ]


def test_search_documents(mcp, engine):
    result, err = call(mcp, "search_documents", {"query": "sqlite"})
    assert not err
    assert result["total"] == 2
    hit = result["hits"][0]
    assert {"doc_id", "title", "rel_path", "score", "snippets"} <= set(hit)
    snip = hit["snippets"][0]
    assert "sqlite" in snip["text"]
    assert "<mark>" not in snip["text"]  # MCP 用户拿到纯文本
    assert snip["start_line"] >= 1 and snip["end_line"] >= snip["start_line"]

    page, _ = call(mcp, "search_documents", {"query": "sqlite", "limit": 1, "offset": 1})
    assert page["total"] == 2 and len(page["hits"]) == 1
    empty, _ = call(mcp, "search_documents", {"query": "   "})
    assert empty["total"] == 0


def test_get_document(mcp, settings, engine):
    did = doc_id(engine, "notes/start.md")
    result, err = call(mcp, "get_document", {"document_id": did})
    assert not err
    assert result["title"] == "知识库系统起步"  # frontmatter title
    assert result["rel_path"] == "notes/start.md"
    assert result["frontmatter"]["tags"] == ["kb", "写作"]
    assert result["headings"][0]["text"] == "开始"
    # 正文必须与磁盘逐字一致（不是 SQLite 里的副本）
    assert result["content"].encode("utf-8") == (settings.raw_root / "notes" / "start.md").read_bytes()


def test_get_document_not_found(mcp):
    result, err = call(mcp, "get_document", {"document_id": 999999})
    assert err
    assert "不存在" in str(result)


def test_list_documents(mcp):
    all_docs, _ = call(mcp, "list_documents", {})
    assert all_docs["total"] == len(CORPUS) + 1  # corpus + uses.md

    by_dir, _ = call(mcp, "list_documents", {"dir": "notes"})
    assert by_dir["total"] == 12
    assert all(it["rel_path"].startswith("notes/") for it in by_dir["items"])

    by_q, _ = call(mcp, "list_documents", {"q": "Landing"})  # title/路径 过滤（与 REST 一致）
    assert by_q["total"] == 1 and by_q["items"][0]["rel_path"] == "misc/eng.md"

    by_status, _ = call(mcp, "list_documents", {"status": "missing"})
    assert by_status["total"] == 0

    paged, _ = call(mcp, "list_documents", {"limit": 5, "offset": 5})
    assert len(paged["items"]) == 5


def test_get_document_links(mcp, engine):
    start_id = doc_id(engine, "notes/start.md")
    eng_id = doc_id(engine, "misc/eng.md")

    result, err = call(mcp, "get_document_links", {"document_id": start_id})
    assert not err
    by_target = {o["target"]: o for o in result["outgoing"]}
    # 已解析的相对链接与 wiki 链接
    assert by_target["../misc/eng.md"]["to_doc"]["id"] == eng_id
    assert by_target["../misc/eng.md"]["broken"] is False
    assert by_target["中文笔记"]["to_doc"]["id"] == doc_id(engine, "notes/中文笔记.md")
    # 断链明确标记
    broken = by_target["不存在目标"]
    assert broken["broken"] is True and broken["to_doc"] is None
    # 外链标记 external
    assert by_target["https://example.org/doc"]["external"] is True

    incoming, _ = call(mcp, "get_document_links", {"document_id": eng_id})
    assert {r["rel_path"] for r in incoming["incoming"]} == {"notes/start.md"}


def test_get_document_assets(mcp, engine):
    did = doc_id(engine, "notes/uses.md")
    result, err = call(mcp, "get_document_assets", {"document_id": did})
    assert not err
    by_path = {a["relative_path"]: a for a in result["items"]}
    assert by_path["assets/logo.png"]["mime_type"] == "image/png"
    assert by_path["assets/logo.png"]["status"] == "indexed"
    assert by_path["files/report.pdf"]["extension"] == ".pdf"
    # 缺失资产（corpus notes/images.md 引用 ../assets/img.png，文件不存在）
    images_doc = doc_id(engine, "notes/images.md")
    res2, _ = call(mcp, "get_document_assets", {"document_id": images_doc})
    assert res2["items"][0]["status"] == "missing"

    _, err3 = call(mcp, "get_document_assets", {"document_id": 999999})
    assert err3


def test_get_knowledge_stats(mcp):
    stats, err = call(mcp, "get_knowledge_stats", {})
    assert not err
    assert stats["document_count"] == len(CORPUS) + 1
    assert stats["indexed_count"] == stats["document_count"]
    assert stats["missing_count"] == 0
    assert stats["last_scan_at"]


def test_tools_do_not_modify_or_delete_raw(mcp, settings, engine):
    """全部工具（含错误路径）轮一遍后，raw/ 逐字节不变。"""
    before = file_snapshot(settings.raw_root)
    did = doc_id(engine, "notes/uses.md")
    call(mcp, "search_documents", {"query": "知识库"})
    call(mcp, "get_document", {"document_id": did})
    call(mcp, "list_documents", {"dir": "notes"})
    call(mcp, "get_document_links", {"document_id": did})
    call(mcp, "get_document_assets", {"document_id": did})
    call(mcp, "get_knowledge_stats", {})
    call(mcp, "get_document", {"document_id": 424242})
    assert file_snapshot(settings.raw_root) == before


def test_path_traversal_guard():
    """raw/ 读取的唯一校验点：穿越/绝对/隐藏路径全部拒绝（严格，容忍规范化输入）。"""
    assert raw_path_for("../../etc/passwd") is None
    assert raw_path_for("/etc/passwd") is None
    assert raw_path_for("a/../../x.md") is None
    assert raw_path_for("a/../b.md") is None  # 含 .. 段的一律拒绝
    assert raw_path_for(".hidden.md") is None
    assert raw_path_for("notes/start.md") is not None  # 正常路径放行
    with pytest.raises(FileNotFoundError):
        read_raw_bytes("../../etc/passwd")


def test_mcp_reads_live_file_after_edit(mcp, settings, engine):
    """正文是实时磁盘状态：改文件 + 重扫后，MCP 读到新内容。"""
    did = doc_id(engine, "notes/special.md")
    write_doc(settings, "notes/special.md", "已更新：面对象新内容。\n")
    run_scan(engine)
    result, err = call(mcp, "get_document", {"document_id": did})
    assert not err
    assert "面对象新内容" in result["content"]
    assert result["content"].encode("utf-8") == (settings.raw_root / "notes" / "special.md").read_bytes()


# ---------- V0.5 Phase 8–9：search_mode / related / knowledge_status ----------

def test_search_documents_defaults_to_smart(mcp, engine):
    result, err = call(mcp, "search_documents", {"query": "sqlite"})
    assert not err
    assert result["search_mode"] == "smart"
    hit = result["hits"][0]
    assert "matched_terms" in hit
    # 无 HTML / 无 <mark> / 无绝对路径
    assert "<mark>" not in hit["snippets"][0]["text"]
    assert result["query"] == "sqlite"


def test_search_documents_keyword_legacy(mcp, engine):
    kw, _ = call(mcp, "search_documents", {"query": "sqlite", "search_mode": "keyword"})
    assert kw["search_mode"] == "keyword"
    assert all("matched_terms" not in h for h in kw["hits"])
    # keyword 保留原始 bm25（可能为负）
    assert isinstance(kw["hits"][0]["score"], (int, float))


def test_smart_recall_equals_keyword(mcp, engine):
    kw, _ = call(mcp, "search_documents", {"query": "sqlite", "search_mode": "keyword"})
    sm, _ = call(mcp, "search_documents", {"query": "sqlite", "search_mode": "smart"})
    assert kw["total"] == sm["total"] == 2
    assert {h["rel_path"] for h in kw["hits"]} == {h["rel_path"] for h in sm["hits"]}


def test_smart_scores_desc_high_is_relevant(mcp, engine):
    sm, err = call(mcp, "search_documents", {"query": "sqlite", "search_mode": "smart"})
    assert not err
    scores = [h["score"] for h in sm["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= 0 for s in scores)


def test_smart_returns_matched_terms(mcp, engine):
    sm, _ = call(mcp, "search_documents", {"query": "sqlite", "search_mode": "smart"})
    hit = sm["hits"][0]
    assert set(hit["matched_terms"]) == {"sqlite"}


def test_invalid_search_mode_is_stable_error(mcp):
    result, err = call(mcp, "search_documents", {"query": "sqlite", "search_mode": "bogus"})
    assert err
    assert "search_mode" in str(result)


def test_find_related_documents(mcp, engine, settings):
    # 复用 corpus：start.md 与 中文笔记 同目录 + 共享标题词（中文笔记）+ 链接
    start_id = doc_by_rel(engine, "notes/start.md")["id"]
    result, err = call(mcp, "find_related_documents", {"document_id": start_id})
    assert not err
    assert result["document_id"] == start_id
    assert start_id not in {it["doc_id"] for it in result["items"]}
    if result["items"]:
        item = result["items"][0]
        assert {"doc_id", "title", "rel_path", "score", "reasons"} <= set(item)
        assert item["reasons"]


def test_find_related_documents_not_found(mcp):
    result, err = call(mcp, "find_related_documents", {"document_id": 999999})
    assert err
    assert "不存在" in str(result)


def test_find_related_missing_document_excluded(corpus, settings, engine, mcp):

    did = doc_by_rel(engine, "notes/start.md")["id"]
    (settings.raw_root / "notes" / "start.md").unlink()
    run_scan(engine)
    result, err = call(mcp, "find_related_documents", {"document_id": did})
    assert err  # 文档已 missing，不在 indexed 集合中 -> 明确错误


def test_get_document_knowledge_status(mcp, engine, knowledge):
    run_scan(engine)
    cases = [
        ("notes/know_true.md", "resolved"),
        ("notes/know_false.md", "unresolved"),
        ("notes/know_state.md", "deprecated"),
        ("notes/know_none.md", None),
        ("notes/start.md", None),  # 无 frontmatter 状态
    ]
    for rel, expected in cases:
        did = doc_by_rel(engine, rel)["id"]
        result, err = call(mcp, "get_document", {"document_id": did})
        assert not err, rel
        assert result["knowledge_status"] == expected, rel


def test_mcp_output_has_no_absolute_paths(mcp, engine):
    result, _ = call(mcp, "search_documents", {"query": "sqlite"})
    joined = json.dumps(result, ensure_ascii=False)
    assert "/home/" not in joined
    assert "knowledge.db" not in joined
    assert "/raw/" not in joined  # 相对路径 rel_path 才是对外形态
    doc, _ = call(mcp, "get_document", {"document_id": result["hits"][0]["doc_id"]})
    assert "/home/" not in json.dumps(doc)
    assert "/raw/" not in json.dumps(doc)


def test_find_related_does_not_touch_raw(corpus, settings, engine, mcp):
    from tests.conftest import file_snapshot as snap

    before = snap(settings.raw_root)
    start_id = doc_by_rel(engine, "notes/start.md")["id"]
    call(mcp, "find_related_documents", {"document_id": start_id})
    call(mcp, "search_documents", {"query": "sqlite", "search_mode": "smart"})
    call(mcp, "find_related_documents", {"document_id": 999999})
    assert snap(settings.raw_root) == before
