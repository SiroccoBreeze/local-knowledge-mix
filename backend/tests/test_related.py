"""V0.5 Phase 6–7：related documents — 可解释综合相关性（无向量）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import get_engine_dep
from app.service.docs import DocNotFoundError
from app.service.related import find_related
from tests.conftest import doc_by_rel, file_snapshot, run_scan, write_doc

# 受控语料（每个特征独立成对，未显式出现即无重叠）
RELEVANT = {
    "alpha/a.md": (
        "---\ntitle: 结账核对说明\ntags: [医保]\n---\n"
        "# 正文\n\n住院结算失败说明。\n\n稽核复审 稽核复审 处理。\n\n"
        "## 稽核要点\n\n故障排查流程。\n"
    ),
    # b：与 a 同目录 + 共享标签 + 标题 3-gram + 正文 3-gram + a→b 显式链接
    "alpha/b.md": (
        "---\ntitle: 结账核对汇总\ntags: [医保]\n---\n# 汇总\n\n"
        "住院结算 对账说明。\n稽核复审 处理。\n"
    ),
    "alpha/c.md": "---\ntitle: 护理排班备忘\ntags: [护理]\n---\n排班 轮转 交接 说明。\n",
    # m：初始与 a 强相关（同目录+同标签）；删除文件后必须从结果消失
    "alpha/m.md": "---\ntitle: 备忘说明\ntags: [医保]\n---\n住院结算 红冲 规则 说明。\n",
    # x：任何特征都不与 a 重叠 → 不得被强行推荐
    "beta/x.md": "# X系统接口文档\n\n接口 联调 事项 说明。\n",
    # d：不同目录/无标签，仅与 a 共享 heading（稽核要点）
    "gamma/d.md": "---\ntitle: 预算超支处理\n---\n费用 报审 说明。\n\n## 稽核要点\n\n复核 流程。\n",
}


@pytest.fixture()
def corpus(settings, engine):
    for rel, content in RELEVANT.items():
        write_doc(settings, rel, content)
    run_scan(engine, full=True)
    return settings


def _ids(items):
    return {it["doc_id"] for it in items}


def test_self_not_recommended(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    out = find_related(engine, a["id"])
    assert a["id"] not in _ids(out["items"])
    assert out["document_id"] == a["id"]


def test_same_directory(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    c = doc_by_rel(engine, "alpha/c.md")
    item = next(it for it in find_related(engine, a["id"])["items"] if it["doc_id"] == c["id"])
    assert "same_directory" in item["reasons"]
    assert item["score"] >= 0.25


def test_shared_tag(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    b = doc_by_rel(engine, "alpha/b.md")
    item = next(it for it in find_related(engine, a["id"])["items"] if it["doc_id"] == b["id"])
    assert "shared_tag" in item["reasons"]


def test_explicit_link_produces_linked_reason(corpus, settings, engine):
    # 补一条 a -> b 的相对链接，重扫后应有 linked reason
    content = RELEVANT["alpha/a.md"] + "\n[b 相关](b.md)\n"
    write_doc(settings, "alpha/a.md", content)
    run_scan(engine)
    a = doc_by_rel(engine, "alpha/a.md")
    b = doc_by_rel(engine, "alpha/b.md")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM links WHERE from_doc=:f AND target='b.md' AND to_doc=:t"),
            {"f": a["id"], "t": b["id"]},
        ).first()
        assert row is not None
    item = next(it for it in find_related(engine, a["id"])["items"] if it["doc_id"] == b["id"])
    assert "linked" in item["reasons"]

    # 反向：对 b 而言 a 是入链来源，同样产生 linked
    item_b = next(
        it for it in find_related(engine, b["id"])["items"] if it["doc_id"] == a["id"]
    )
    assert "linked" in item_b["reasons"]


def test_title_similarity(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    b = doc_by_rel(engine, "alpha/b.md")
    item = next(it for it in find_related(engine, a["id"])["items"] if it["doc_id"] == b["id"])
    assert "title_similarity" in item["reasons"]


def test_heading_similarity(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    d = doc_by_rel(engine, "gamma/d.md")
    item = next(it for it in find_related(engine, a["id"])["items"] if it["doc_id"] == d["id"])
    assert "heading_similarity" in item["reasons"]


def test_term_similarity(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    b = doc_by_rel(engine, "alpha/b.md")
    item = next(it for it in find_related(engine, a["id"])["items"] if it["doc_id"] == b["id"])
    assert "term_similarity" in item["reasons"]


def test_score_desc_and_deterministic(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    out1 = find_related(engine, a["id"])
    out2 = find_related(engine, a["id"])
    scores = [it["score"] for it in out1["items"]]
    assert scores == sorted(scores, reverse=True)
    assert [(it["doc_id"], it["score"], tuple(it["reasons"])) for it in out1["items"]] == [
        (it["doc_id"], it["score"], tuple(it["reasons"])) for it in out2["items"]
    ]


def test_missing_doc_not_recommended(corpus, settings, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    m = doc_by_rel(engine, "alpha/m.md")
    assert any(it["doc_id"] == m["id"] for it in find_related(engine, a["id"])["items"])
    # 删除文件 + 重扫 → m 变 missing，必须从相关结果消失
    (settings.raw_root / "alpha" / "m.md").unlink()
    run_scan(engine)
    assert m["id"] not in _ids(find_related(engine, a["id"])["items"])


def test_dissimilar_not_forced(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    x = doc_by_rel(engine, "beta/x.md")
    assert x["id"] not in _ids(find_related(engine, a["id"])["items"])
    # 完全没有共同特征的文档作为锚点 → 空结果（不硬凑）
    assert find_related(engine, x["id"])["items"] == []


def test_limit(corpus, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    out = find_related(engine, a["id"], limit=2)
    assert len(out["items"]) == 2


def test_document_not_found(corpus, engine):
    with pytest.raises(DocNotFoundError):
        find_related(engine, 999999)


def test_reads_nothing_and_writes_nothing(corpus, settings, engine):
    """相关计算只读：raw/ 逐字节不变。"""
    before = file_snapshot(settings.raw_root)
    a = doc_by_rel(engine, "alpha/a.md")
    b = doc_by_rel(engine, "alpha/b.md")
    find_related(engine, a["id"])
    find_related(engine, b["id"])
    find_related(engine, 999999 if False else a["id"])
    assert file_snapshot(settings.raw_root) == before


@pytest.fixture()
def client(settings, corpus, engine):
    from app.main import app

    app.dependency_overrides[get_engine_dep] = lambda: engine
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_engine_dep, None)


def test_api_related_endpoint(client, engine):
    a = doc_by_rel(engine, "alpha/a.md")
    r = client.get(f"/api/v1/documents/{a['id']}/related", params={"limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["document_id"] == a["id"]
    assert 0 < len(body["items"]) <= 3
    item = body["items"][0]
    assert {"doc_id", "title", "rel_path", "score", "reasons"} <= set(item)
    # 不泄漏绝对路径/正文/DB 内部字段
    assert "/raw/" not in json_ref(body)
    assert not any("sha256" in k or "mtime" in k for k in item)


def json_ref(body) -> str:
    import json

    return json.dumps(body)


def test_api_related_404(client):
    r = client.get("/api/v1/documents/999999/related")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "DOC_NOT_FOUND"
