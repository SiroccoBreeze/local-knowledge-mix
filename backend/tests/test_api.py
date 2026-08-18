"""API surface: health, scan, documents, content-from-disk, search, neighbors."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_engine_dep
from tests.conftest import CORPUS


@pytest.fixture()
def client(settings, engine, corpus):
    from app.main import app

    app.dependency_overrides[get_engine_dep] = lambda: engine
    with TestClient(app) as c:
        c.post("/api/v1/scan", json={"full": True})
        yield c
    app.dependency_overrides.pop(get_engine_dep, None)


def _doc_id(client, rel: str) -> int:
    items = client.get("/api/v1/documents", params={"q": rel}).json()["items"]
    for item in items:
        if item["rel_path"] == rel:
            return item["id"]
    raise AssertionError(f"{rel} not found")


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["last_scan_at"] is not None
    assert body["last_scan_report"]["total_docs"] == len(CORPUS)


def test_scan_endpoint_and_status(client):
    r = client.post("/api/v1/scan", json={"full": False})
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 0 and body["unchanged"] == len(CORPUS)

    status = client.get("/api/v1/scan/status").json()
    assert status["last_scan_report"] == body
    assert status["last_scan_at"] is not None


def test_documents_listing_and_filters(client):
    all_docs = client.get("/api/v1/documents", params={"limit": 500}).json()
    assert all_docs["total"] == len(CORPUS)

    notes_only = client.get("/api/v1/documents", params={"dir": "notes"}).json()
    assert notes_only["total"] == 11  # notes/* 下的文件数
    assert all(it["rel_path"].startswith("notes/") for it in notes_only["items"])

    missing_filter = client.get("/api/v1/documents", params={"status": "missing"}).json()
    assert missing_filter["total"] == 0


def test_document_meta_fields(client):
    doc_id = _doc_id(client, "notes/start.md")
    meta = client.get(f"/api/v1/documents/{doc_id}").json()
    assert meta["title"] == "知识库系统起步"  # 来自 frontmatter
    assert meta["frontmatter"]["tags"] == ["kb", "写作"]
    assert meta["headings"][0]["text"] == "开始"
    assert "plain_text" not in meta and "body" not in meta  # 元数据不含正文


def test_content_is_byte_identical_to_disk(client, settings):
    doc_id = _doc_id(client, "misc/eng.md")
    r = client.get(f"/api/v1/documents/{doc_id}/content")
    assert r.status_code == 200
    on_disk = (settings.raw_root / "misc" / "eng.md").read_bytes()
    assert r.content == on_disk  # 逐字节一致 —— 正文从未存库
    assert r.headers["Etag"]
    assert r.headers["X-Doc-Sha256"] == _sha(settings, "misc/eng.md")


def test_content_404(client):
    assert client.get("/api/v1/documents/999999/content").status_code == 404
    assert client.get("/api/v1/documents/999999").status_code == 404


def test_search_endpoint(client):
    r = client.get("/api/v1/search", params={"q": "sqlite"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    hit = body["hits"][0]
    assert hit["doc"]["title"]
    assert any("sqlite" in s["text"] for s in hit["snippets"])


def test_search_markup_and_line_numbers(client):
    r = client.get("/api/v1/search", params={"q": '"exact phrase"'})
    body = r.json()
    assert body["total"] == 1
    snip = body["hits"][0]["snippets"][0]
    assert "<mark>" in snip["text"]
    assert snip["start_line"] >= 1


def test_search_is_empty_filtered(client, settings):
    # 磁盘删除文档并重扫后，其内容必须从搜索结果消失（且 content 端点 404）
    doc_id = _doc_id(client, "notes/start.md")
    (settings.raw_root / "notes" / "start.md").unlink()
    client.post("/api/v1/scan", json={})
    assert client.get("/api/v1/search", params={"q": "hello"}).json()["total"] == 0
    assert client.get(f"/api/v1/documents/{doc_id}/content").status_code == 404  # 磁盘已不存在


def test_search_bad_query_is_400(client):
    r = client.get("/api/v1/search", params={"q": "-"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "EMPTY_QUERY"
    r2 = client.get("/api/v1/search", params={"q": "  (  )  "})
    assert r2.status_code == 400


def test_neighbors_endpoint(client):
    start_id = _doc_id(client, "notes/start.md")
    eng_id = _doc_id(client, "misc/eng.md")

    out = client.get(f"/api/v1/documents/{start_id}/neighbors").json()["outgoing"]
    targets = {(n["rel_path"], n["kind"], n["target"]) for n in out}
    assert ("misc/eng.md", "relative", "../misc/eng.md") in targets
    assert ("notes/中文笔记.md", "wiki", "中文笔记") in targets
    # url 与悬挂链接不进 outgoing（to_doc 为 NULL）
    assert all(n["kind"] != "url" for n in out)

    inc = client.get(f"/api/v1/documents/{eng_id}/neighbors").json()["incoming"]
    assert {n["rel_path"] for n in inc} == {"notes/start.md"}


def test_api_rejects_unknown_doc(client):
    assert client.get("/api/v1/documents/123456").status_code == 404
    assert client.get("/api/v1/documents/123456/neighbors").status_code == 404


def _sha(settings, rel: str) -> str:
    import hashlib

    return hashlib.sha256((settings.raw_root / rel).read_bytes()).hexdigest()


def test_content_type_and_etag(client, settings):
    doc_id = _doc_id(client, "notes/start.md")
    r = client.get(f"/api/v1/documents/{doc_id}/content")
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["Etag"] == f'"{_sha(settings, "notes/start.md")[:16]}"'
