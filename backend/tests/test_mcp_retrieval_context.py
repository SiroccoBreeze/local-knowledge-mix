"""V0.6 Phase 13 — retrieve_context MCP tool."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.mcp.server import make_server
from tests.conftest import doc_by_rel, run_scan

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" + b"\xff" * 16
PDF = b"%PDF-1.4 fake pdf bytes\n"


@pytest.fixture()
def assets(settings):
    from tests.conftest import write_bytes, write_doc

    write_bytes(settings, "assets/logo.png", PNG)
    write_bytes(settings, "files/report.pdf", PDF)
    write_doc(settings, "notes/uses.md", "# 引用\n\n![图](../assets/logo.png)\n")


@pytest.fixture()
def mcp(corpus, engine, assets):
    run_scan(engine, full=True)
    return make_server(engine)


def call(server, name: str, args: dict) -> tuple[dict | list | str, bool]:
    try:
        contents = asyncio.run(server.call_tool(name, args))
    except Exception as exc:
        return str(exc), True
    if not contents:
        return None, False
    text = contents[0].text if hasattr(contents[0], "text") else str(contents[0])
    try:
        return json.loads(text), False
    except json.JSONDecodeError:
        return text, False


def test_registers_eight_tools(mcp):
    names = sorted(t.name for t in asyncio.run(mcp.list_tools()))
    assert names == [
        "find_related_documents",
        "get_document",
        "get_document_assets",
        "get_document_links",
        "get_knowledge_stats",
        "list_documents",
        "retrieve_context",
        "search_documents",
    ]


def test_retrieve_context_basic(mcp, engine):
    result, err = call(mcp, "retrieve_context", {"query": "sqlite", "limit": 2})
    assert not err
    assert result["query"] == "sqlite"
    assert result["total"] == 2
    assert len(result["items"]) <= 2
    assert result["context"]
    assert "<mark>" not in result["context"]
    assert "/home/" not in result["context"]


def test_retrieve_context_with_related(mcp, engine):
    start_id = doc_by_rel(engine, "notes/start.md")["id"]
    result, err = call(mcp, "retrieve_context", {"query": "sqlite", "limit": 3, "include_related": True, "document_id": start_id})
    assert not err
    assert result["query"] == "sqlite"
    assert result["context"]
    assert "<mark>" not in result["context"]


def test_retrieve_context_document_only(mcp, engine):
    start_id = doc_by_rel(engine, "notes/start.md")["id"]
    result, err = call(mcp, "retrieve_context", {"query": "", "limit": 3, "include_related": True, "document_id": start_id})
    assert not err
    assert result["context"]
    # 文档自身的 title 应在 context 中（related 包含它引用的文档）
    assert "知识库系统起步" in result["context"] or "笔" in result["context"]


def test_retrieve_context_empty_query_error(mcp):
    result, err = call(mcp, "retrieve_context", {"query": "  "})
    assert err
    assert "空" in str(result) or "不可为空" in str(result)


def test_retrieve_context_nonexistent_document(mcp):
    result, err = call(mcp, "retrieve_context", {"query": "", "document_id": 999999})
    assert err
    assert "不存在" in str(result)


def test_retrieve_context_no_security_leak(mcp, engine):
    """对抗验证：context 不泄漏任何敏感信息。"""
    result, err = call(mcp, "retrieve_context", {"query": "sqlite", "limit": 3})
    assert not err
    ctx = result["context"]
    for forbidden in ("<mark>", "<script>", "alert(", "/home/", "/raw/", "knowledge.db", "SELECT * FROM", "INSERT INTO", "DELETE FROM"):
        assert forbidden not in ctx, f"leak: {forbidden}"


def test_retrieve_context_deterministic(mcp, engine):
    a, _ = call(mcp, "retrieve_context", {"query": "sqlite", "limit": 2})
    b, _ = call(mcp, "retrieve_context", {"query": "sqlite", "limit": 2})
    assert a["context"] == b["context"]


def test_retrieve_context_max_chars(mcp, engine):
    result, _ = call(mcp, "retrieve_context", {"query": "sqlite", "limit": 5, "max_chars": 200})
    assert len(result["context"]) <= 500


def test_existing_7_tools_still_work(mcp, engine):
    # 原有工具全部保持可用
    result, err = call(mcp, "search_documents", {"query": "sqlite"})
    assert not err and result["total"] == 2
    doc_id = result["hits"][0]["doc_id"]
    doc, err = call(mcp, "get_document", {"document_id": doc_id})
    assert not err and doc["title"]
    lst, err = call(mcp, "list_documents", {"limit": 3})
    assert not err and lst["total"] > 0
    links, err = call(mcp, "get_document_links", {"document_id": doc_id})
    assert not err
    assets, err = call(mcp, "get_document_assets", {"document_id": doc_id})
    assert not err
    related, err = call(mcp, "find_related_documents", {"document_id": doc_id})
    assert not err
    stats, err = call(mcp, "get_knowledge_stats", {})
    assert not err and stats["document_count"] > 0


def test_retrieve_context_does_not_touch_raw(corpus, settings, engine, mcp):
    from tests.conftest import file_snapshot as snap

    before = snap(settings.raw_root)
    call(mcp, "retrieve_context", {"query": "sqlite", "limit": 2})
    call(mcp, "retrieve_context", {"query": "", "document_id": 999999})
    assert snap(settings.raw_root) == before
