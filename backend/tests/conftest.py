"""Shared fixtures: isolated settings, engine, and the standard corpus."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import app.config as config_module
from app.config import Settings

# The fixture matrix: every parsing/scanning concern from the phase-1 spec.
CORPUS: dict[str, str] = {
    "notes/start.md": (
        "---\ntitle: 知识库系统起步\ntags: [kb, 写作]\n---\n"
        "# 开始\n\n"
        "这是 **知识库系统** 的核心文档。\n\n"
        "参考 [[中文笔记]]、[[不存在目标]]、\n"
        "[相对路径链接](../misc/eng.md)、[外部](https://example.org/doc)、\n"
        "![图片](../assets/pic.png)。\n\n"
        "```python\nprint(\"hello world\")\n```\n"
    ),
    "notes/中文笔记.md": (
        "---\ntitle: 深度中文笔记\ntags: [中文]\n---\n# 中文标题\n\n"
        "知识库系统需要良好支持中文检索。绝对证据连接。\n"
    ),
    "notes/no_h1.md": "无标题文档，正文里没有一级标题。开头直接是正文。\n",
    "notes/no_frontmatter.md": "# 无元数据文档\n\n只有标题和正文，没有 YAML 段。\n",
    "notes/frontmatter_broken.md": "---\ntitle: [未闭合\n---\n正文还能用。\n",
    "notes/images.md": "![本地图片](../assets/img.png)\n\n![](https://cdn.example.com/x.png)\n\n图片引用不会被当作文档链接。\n",
    "notes/special.md": "特殊字符：→ 箭头、café、emoji 🔥、<tag>、\"引号\"、a_b_c、50%+。\n",
    "notes/empty.md": "",
    "notes/code.md": "```rust\nfn main() { println!(\"rust code\"); }\n```\n代码块外文字。\n",
    "notes/snippet_hunt.md": "\n\n正文字段很长，包含 exact phrase 关键短语用于验证短语查询。\n",
    "notes/ai.md": "---\ntitle: AI 基础概念\n---\n人工智能基础概念概述。\n",
    "misc/eng.md": (
        "---\ntitle: English Landing\n---\n# English\n\n"
        "This document mentions sqlite search engine paragraph. "
        "zlinuxpenguin is a unique term.\n"
    ),
    "misc/rejected.md": "sqlite 包含 排除词 的文档。\n",
    "deep/link_target.md": "被链接的目标文档。\n",
    "deep/zh_序列.md": "中文文档 序列化 单元测试 覆盖。\n",
}


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    """Isolated raw/ + db under tmp_path; patches app.config.settings."""
    raw = tmp_path / "raw"
    raw.mkdir()
    s = Settings(raw_root=raw, db_path=tmp_path / "data" / "kb.db")
    monkeypatch.setattr(config_module, "settings", s)
    return s


@pytest.fixture()
def engine(settings):
    from app.db.engine import get_engine

    eng = get_engine()
    yield eng
    eng.dispose()


@pytest.fixture()
def corpus(settings) -> dict[str, str]:
    """Write the standard corpus into raw/; returns rel -> content."""
    for rel, content in CORPUS.items():
        write_doc(settings, rel, content)
    return dict(CORPUS)


def write_doc(settings: Settings, rel: str, content: str) -> Path:
    path = settings.raw_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_bytes(settings: Settings, rel: str, data: bytes) -> Path:
    path = settings.raw_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def file_snapshot(root: Path) -> dict[str, str]:
    """rel_path -> sha256 for every file under root (the read-only proof)."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def run_scan(engine, *, full: bool = False):
    from app.scanner import run_scan as _run_scan

    return _run_scan(engine, full=full)


def search(engine, q, *, limit: int = 20, offset: int = 0):
    from app.search.query import search as _search

    return _search(engine, q, limit=limit, offset=offset)


def doc_by_rel(engine, rel: str) -> dict | None:
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM documents WHERE rel_path = :p"), {"p": rel}
        ).mappings().first()
        return dict(row) if row else None
