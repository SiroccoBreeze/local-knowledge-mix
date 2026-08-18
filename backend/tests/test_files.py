"""Safe media endpoint: serves images under raw/ without exposing the root."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_engine_dep
from tests.conftest import write_bytes, write_doc

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" + b"\xff" * 16


@pytest.fixture()
def client(settings, engine, corpus):
    from app.main import app

    write_bytes(settings, "assets/logo.png", PNG)
    write_bytes(settings, "assets/pic.JPG", b"fake-jpg-bytes")
    write_bytes(settings, "assets/.hidden.png", PNG)
    write_doc(settings, "notes/start.md", "# 标题\n")

    app.dependency_overrides[get_engine_dep] = lambda: engine
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_engine_dep, None)


def test_serves_image_bytes_identical_to_disk(client, settings):
    r = client.get("/api/v1/raw/assets/logo.png")
    assert r.status_code == 200
    assert r.content == (settings.raw_root / "assets" / "logo.png").read_bytes()
    assert r.headers["content-type"].startswith("image/png")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_case_insensitive_extension(client):
    r = client.get("/api/v1/raw/assets/pic.JPG")
    assert r.status_code == 200


def test_traversal_attempts_refused(client):
    attempts = [
        "/api/v1/raw/../system/purpose.md",
        "/api/v1/raw/..%2Fsystem%2Fpurpose.md",
        "/api/v1/raw/..%2F..%2Fetc%2Fpasswd",
        "/api/v1/raw/etc/passwd",
        "/api/v1/raw/%2e%2e/system/purpose.md",
        "/api/v1/raw/a/../../etc/passwd",
    ]
    for url in attempts:
        r = client.get(url)
        assert r.status_code in (404, 403), f"{url} -> {r.status_code}"


def test_markdown_body_not_served_here(client):
    # 正文有专属端点；此接口不得泄露 .md 内容
    r = client.get("/api/v1/raw/notes/start.md")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


def test_hidden_files_refused(client):
    assert client.get("/api/v1/raw/assets/.hidden.png").status_code == 404


def test_missing_and_directory_refused(client):
    assert client.get("/api/v1/raw/assets/nope.png").status_code == 404
    assert client.get("/api/v1/raw/assets").status_code == 404  # 目录不暴露
    assert client.get("/api/v1/raw/assets/").status_code == 404


def test_absolute_path_refused(client):
    assert client.get("/api/v1/raw//etc/passwd").status_code == 404
