"""Asset discovery/persistence/safety + share-page checks (V0.3)."""

from __future__ import annotations

import hashlib
import textwrap

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import get_engine_dep
from app.config import REPO_ROOT
from tests.conftest import CORPUS, doc_by_rel, file_snapshot, run_scan, write_bytes, write_doc

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" + b"\xff" * 16
PDF = b"%PDF-1.4 fake pdf bytes \x00\x01\n"
ZIP = b"PK\x03\x04 fake zip bytes"
TXT = "纯文本附件内容。\n".encode()

USES_ASSETS = textwrap.dedent(
    """\
    # 引用资产

    ![图](../assets/logo.png) 与 [附件](../files/report.pdf)

    [同上图](../assets/logo.png) 与 [不存在的](../files/gone.zip)
    """
)


def _rows(engine, sql: str = "SELECT * FROM assets") -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql)).mappings().all()]


@pytest.fixture()
def with_assets(settings):
    """Corpus + 真实存在的图片/PDF/zip/txt + 缺失引用 + 穿越引用。"""
    from tests.conftest import CORPUS as _CORPUS

    for rel, content in _CORPUS.items():
        write_doc(settings, rel, content)
    write_bytes(settings, "assets/logo.png", PNG)
    write_bytes(settings, "assets/logo2.png", PNG)  # 两个文档共用同一张图
    write_bytes(settings, "files/report.pdf", PDF)
    write_bytes(settings, "files/conf.zip", ZIP)
    write_bytes(settings, "files/note.txt", TXT)
    write_doc(settings, "notes/uses_assets.md", USES_ASSETS)
    write_doc(settings, "notes/shared.md", "[共用图](../assets/logo.png) 与 [图2](../assets/logo2.png)\n")
    write_doc(settings, "notes/second.md", "[共图2](../assets/logo2.png)\n")
    write_doc(
        settings,
        "notes/escape.md",
        "![逃逸](../../../../secret.png) 图片引用与 ![绝对](/etc/passwd.png)\n",
    )
    return settings


@pytest.fixture()
def client(settings, engine, with_assets):
    from app.main import app

    app.dependency_overrides[get_engine_dep] = lambda: engine
    with TestClient(app) as c:
        c.post("/api/v1/scan", json={"full": True})
        yield c
    app.dependency_overrides.pop(get_engine_dep, None)


def test_asset_discovery_and_fields(with_assets, engine):
    run_scan(engine, full=True)
    rows = {r["relative_path"]: r for r in _rows(engine)}

    logo = rows["assets/logo.png"]
    assert logo["filename"] == "logo.png"
    assert logo["extension"] == ".png"
    assert logo["mime_type"] == "image/png"
    assert logo["size"] == len(PNG)
    assert logo["sha256"] == hashlib.sha256(PNG).hexdigest()
    assert logo["status"] == "indexed"

    pdf = rows["files/report.pdf"]
    assert pdf["extension"] == ".pdf"
    assert pdf["mime_type"] == "application/pdf"
    assert pdf["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_missing_asset_tracked_and_relative_paths(with_assets, engine):
    run_scan(engine, full=True)
    rows = _rows(engine)

    # corpus 里 notes/images.md 引用 ../assets/img.png（文件不存在）
    broken = [r for r in rows if r["relative_path"] == "assets/img.png"]
    assert broken and broken[0]["status"] == "missing"
    assert broken[0]["sha256"] == ""

    # 引用了不存在的 zip
    assert any(r["relative_path"] == "files/gone.zip" and r["status"] == "missing" for r in rows)


def test_escape_and_absolute_refs_ignored(with_assets, engine):
    run_scan(engine, full=True)
    paths = {r["relative_path"] for r in _rows(engine)}
    assert "secret.png" not in paths
    assert "etc/passwd.png" not in paths
    assert not any(".." in p for p in paths)


def test_markdown_asset_linkage(with_assets, engine):
    run_scan(engine, full=True)
    doc = doc_by_rel(engine, "notes/uses_assets.md")
    rows = [r for r in _rows(engine) if r["document_id"] == doc["id"]]
    rels = {r["relative_path"]: r for r in rows}
    # 同一 doc 引用同一文件两次 → 只保留一行
    assert len(rows) == 3
    assert "assets/logo.png" in rels and "files/report.pdf" in rels and "files/gone.zip" in rels


def test_shared_asset_two_documents(with_assets, engine):
    run_scan(engine, full=True)
    shared = [r for r in _rows(engine) if r["relative_path"] == "assets/logo2.png"]
    assert len(shared) == 2
    doc_ids = {r["document_id"] for r in shared}
    assert doc_ids == {
        doc_by_rel(engine, "notes/shared.md")["id"],
        doc_by_rel(engine, "notes/second.md")["id"],
    }


def test_asset_hash_updates_on_file_change(with_assets, settings, engine):
    run_scan(engine, full=True)
    before = next(r for r in _rows(engine) if r["relative_path"] == "assets/logo.png")

    write_bytes(settings, "assets/logo.png", b"NEW CONTENT BYTES" * 3)
    assert run_scan(engine).unchanged >= len(CORPUS) + 3
    after = next(r for r in _rows(engine) if r["relative_path"] == "assets/logo.png")
    assert after["sha256"] == hashlib.sha256(b"NEW CONTENT BYTES" * 3).hexdigest()
    assert after["size"] == len(b"NEW CONTENT BYTES" * 3)
    assert after["status"] == "indexed"
    assert before["sha256"] != after["sha256"]


def test_asset_delete_then_recreate(with_assets, settings, engine):
    run_scan(engine, full=True)
    (settings.raw_root / "assets" / "logo.png").unlink()
    run_scan(engine)
    row = next(r for r in _rows(engine) if r["relative_path"] == "assets/logo.png")
    assert row["status"] == "missing"
    # 自愈：重新出现 → 回到 indexed 并带新哈希
    write_bytes(settings, "assets/logo.png", PNG + b"x")
    run_scan(engine)
    row = next(r for r in _rows(engine) if r["relative_path"] == "assets/logo.png")
    assert row["status"] == "indexed"
    assert row["sha256"] == hashlib.sha256(PNG + b"x").hexdigest()


def test_prune_when_reference_removed(with_assets, settings, engine):
    run_scan(engine, full=True)
    doc = doc_by_rel(engine, "notes/uses_assets.md")
    assert any(r["relative_path"] == "files/report.pdf" and r["document_id"] == doc["id"] for r in _rows(engine))

    # 编辑文档：撤掉 pdf 引用
    write_doc(settings, "notes/uses_assets.md", "![图](../assets/logo.png)\n")
    run_scan(engine)
    rows = [r for r in _rows(engine) if r["document_id"] == doc["id"]]
    assert [r["relative_path"] for r in rows] == ["assets/logo.png"]
    # 他人引用不受影响
    assert any(r["relative_path"] == "assets/logo.png" and r["document_id"] != doc["id"] for r in _rows(engine))


def test_scan_with_assets_never_touches_raw(with_assets, settings, engine):
    before = file_snapshot(settings.raw_root)
    run_scan(engine, full=True)
    assert file_snapshot(settings.raw_root) == before


def test_raw_endpoint_serves_new_types_and_zips(client):
    r = client.get("/api/v1/raw/assets/logo.png")
    assert r.status_code == 200 and r.content == PNG
    assert client.get("/api/v1/raw/files/report.pdf").headers["content-type"] == "application/pdf"

    zip_r = client.get("/api/v1/raw/files/conf.zip")
    assert zip_r.status_code == 200
    assert zip_r.headers["content-type"] == "application/zip"
    assert "attachment" in zip_r.headers["content-disposition"]

    txt_r = client.get("/api/v1/raw/files/note.txt")
    assert txt_r.headers["content-type"].startswith("text/plain")
    assert "attachment" not in txt_r.headers.get("content-disposition", "")
    # 缺失文件 / markdown / 穿越依旧被拒
    assert client.get("/api/v1/raw/files/gone.zip").status_code == 404
    assert client.get("/api/v1/raw/notes/start.md").status_code == 403
    assert client.get("/api/v1/raw/..%2FREADME.md").status_code == 404


def test_asset_api(client, engine):
    doc = doc_by_rel(engine, "notes/uses_assets.md")
    items = client.get(f"/api/v1/documents/{doc['id']}/assets").json()
    assert [a["relative_path"] for a in items] == [
        "assets/logo.png",
        "files/gone.zip",
        "files/report.pdf",
    ]
    logo = next(a for a in items if a["filename"] == "logo.png")
    assert logo["mime_type"] == "image/png"
    assert logo["sha256"] == hashlib.sha256(PNG).hexdigest()

    single = client.get(f"/api/v1/assets/{logo['id']}").json()
    assert single["relative_path"] == "assets/logo.png"
    assert single["document_id"] == doc["id"]

    assert client.get("/api/v1/assets/999999").status_code == 404
    assert client.get("/api/v1/documents/999999/assets").status_code == 404


@pytest.mark.skipif(
    not (REPO_ROOT / "frontend" / "dist" / "index.html").exists(),
    reason="frontend/dist 未构建（npm run build）",
)
def test_share_page_served(client):
    r = client.get("/share/42")
    assert r.status_code == 200
    assert '<div id="root">' in r.text
    assert client.get("/").status_code == 200


def test_share_flow_never_modifies_raw(client, settings):
    """Share 页面用到的整条只读链路走一遍，raw/ 必须逐字节不变。"""
    before = file_snapshot(settings.raw_root)
    docs = client.get("/api/v1/documents", params={"limit": 500}).json()["items"]
    for d in docs[:3]:
        client.get(f"/api/v1/documents/{d['id']}")
        client.get(f"/api/v1/documents/{d['id']}/content")
        client.get(f"/api/v1/documents/{d['id']}/neighbors")
        client.get(f"/api/v1/documents/{d['id']}/assets")
    client.get("/api/v1/raw/assets/logo.png")
    client.get("/api/v1/search", params={"q": "sqlite"})
    client.get("/share/1") if (REPO_ROOT / "frontend" / "dist" / "index.html").exists() else None
    assert file_snapshot(settings.raw_root) == before
