"""Read-only markdown parsing for the scanner.

Pure functions: text -> parsed structure. No file I/O, no writes.
The output is deliberately lossy for indexing purposes (markers stripped),
but never loses *content*: code blocks and URLs stay searchable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import ASSET_EXTENSIONS

FRONTMATTER_OPEN = "---"
_CLOSE_FENCE_RE = re.compile(r"(?m)^---[ \t]*\r?$")
_HEADING_RE = re.compile(r"(?m)^([#]{1,6})[ \t]+(.+?)[ \t]*\r?$")
_WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_PAREN_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
# Asset 引用用宽松版本：允许文件名含空格（图片/附件的路径可能带空格）
_ASSET_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_FENCE_LINE_RE = re.compile(r"^\s*(?:```|~~~)")
_FENCE_RE = re.compile(r"(?ms)^```[^\n]*$(.*?)^```[ \t]*\r?$")
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_REF_USE_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_REF_DEF_RE = re.compile(r"(?m)^\[[^\]]+\]:[ \t]+\S+.*\r?$")
_HTML_RE = re.compile(r"<[^>]+>")
_BLOCKQUOTE_RE = re.compile(r"(?m)^[ \t]*>[ \t]?")
_UL_RE = re.compile(r"(?m)^[ \t]*[-+*][ \t]+")
_OL_RE = re.compile(r"(?m)^[ \t]*\d+\.[ \t]+")
_THEMATIC_RE = re.compile(r"(?m)^[ \t]*(?:-{3,}|={3,}|\*{3,}|_{3,})[ \t]*\r?$")
_STRIKE_RE = re.compile(r"~~([^~]+)~~")
_FOOTNOTE_RE = re.compile(r"\[\^[^\]]*\]")
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]+")
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")

Link = tuple[str, str]  # (kind, target) with kind in {"wiki", "relative", "url"}


@dataclass
class ParsedDoc:
    title: str
    frontmatter: dict | None  # metadata only — never the body
    headings: list[dict]  # [{"level": int, "text": str}]
    plain_text: str  # indexable text (markers stripped, content kept)
    links: list[Link]
    asset_refs: list[str]
    word_count: int
    char_count: int
    line_count: int
    scan_error: str | None


def parse_markdown(text: str, rel_path: str) -> ParsedDoc:
    """Parse one markdown document (content already read from disk)."""
    text = text.lstrip("\ufeff")  # tolerate a UTF-8 BOM
    body, meta, fm_error = extract_frontmatter(text)
    headings = extract_headings(body)
    title = title_of(meta, headings, rel_path)
    plain = to_plain_text(body)
    word_count, _ = _count_words(plain)
    return ParsedDoc(
        title=title,
        frontmatter=meta,
        headings=headings,
        plain_text=plain,
        links=extract_links(body),
        asset_refs=extract_asset_refs(body),
        word_count=word_count,
        char_count=len(plain),
        line_count=len(body.splitlines()),
        scan_error=fm_error,
    )


def extract_asset_refs(body: str) -> list[str]:
    """Media/attachment paths referenced by a document, in order, deduped.

    Only targets whose extension is in ASSET_EXTENSIONS count (never .md —
    those are document links). Fragments (#…) and query strings are stripped;
    URLs / absolute paths are skipped; fenced code blocks are ignored.
    """
    refs: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _ASSET_LINK_RE.finditer(line):
            target = match.group(1).strip()
            if not target or "://" in target or target.lower().startswith(("data:", "mailto:")):
                continue
            base = target.split("#", 1)[0].split("?", 1)[0].strip()
            if not base:
                continue
            while base.startswith("./"):  # 仅移除 './' 前缀，保留 '../' 供解析器处理
                base = base[2:]
            if Path(base).suffix.lower() not in ASSET_EXTENSIONS:
                continue
            if base not in refs:
                refs.append(base)
    return refs


def extract_frontmatter(text: str) -> tuple[str, dict | None, str | None]:
    """Split into (body, frontmatter metadata, error-string).

    - No leading ``---``          -> no frontmatter, whole text is body.
    - Opening fence w/o closing   -> broken; body unchanged, error set.
    - Non-mapping / bad YAML      -> broken; body unchanged, error set.
    A broken frontmatter never loses content: the block stays in the body.
    """
    if not text.startswith(FRONTMATTER_OPEN):
        return text, None, None

    closing = _CLOSE_FENCE_RE.search(text, len(FRONTMATTER_OPEN) + 1)
    if closing is None:
        return text, None, "frontmatter: '---' 起始但缺少闭合分隔符"
    block = text[len(FRONTMATTER_OPEN) : closing.start()]
    body = text[closing.end() :].lstrip("\r\n")

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        return text, None, f"frontmatter: YAML 解析失败: {exc}"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return text, None, f"frontmatter: 顶层必须是映射，实际为 {type(data).__name__}"
    return body, data, None


def title_of(meta: dict | None, headings: list[dict], rel_path: str) -> str:
    if meta:
        candidate = meta.get("title")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    for heading in headings:
        if heading["level"] == 1:
            return heading["text"]
    return Path(rel_path).stem


def extract_headings(body: str) -> list[dict]:
    return [
        {"level": len(m.group(1)), "text": m.group(2).strip()}
        for m in _HEADING_RE.finditer(body)
    ]


def extract_links(body: str) -> list[Link]:
    links: list[Link] = []
    for raw in _WIKI_LINK_RE.findall(body):
        target = raw.split("|", 1)[0].strip()
        if target:
            links.append(("wiki", target))
    for _text, target in _PAREN_LINK_RE.findall(body):
        target = target.strip()
        if target.startswith(("http://", "https://")):
            links.append(("url", target))
        elif target.split("#", 1)[0].endswith(".md"):
            links.append(("relative", target.split("#", 1)[0]))
    return links


def to_plain_text(md: str) -> str:
    """Strip markdown markers for indexing. Content is never discarded:
    code blocks stay verbatim, link/image URLs stay searchable."""
    t = md
    t = _FENCE_RE.sub(r"\1", t)  # fenced code -> keep inner text, drop fences/lang
    t = _INLINE_CODE_RE.sub(r"\1", t)  # inline code -> literal text
    t = _PAREN_LINK_RE.sub(r"\1 \2", t)  # links/images -> text/alt + url
    t = _REF_USE_RE.sub(r"\1", t)  # [text][ref] -> text
    t = _REF_DEF_RE.sub("", t)  # [ref]: url definition lines
    t = _HTML_RE.sub("", t)  # html tags (autolinks keep their bare URL)
    t = _HEADING_RE.sub(r"\2", t)  # heading markers, text kept
    t = _BLOCKQUOTE_RE.sub("", t)
    t = _UL_RE.sub(" ", t)
    t = _OL_RE.sub(" ", t)
    t = _THEMATIC_RE.sub("", t)  # --- / ***  hr lines
    t = _STRIKE_RE.sub(r"\1", t)
    t = re.sub(r"\*+", "", t)  # bold/italic asterisks
    t = _FOOTNOTE_RE.sub("", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _count_words(text: str) -> tuple[int, int]:
    """Approximate word count: CJK character-runs + ASCII words."""
    words = len(_CJK_RE.findall(text)) + len(_ASCII_WORD_RE.findall(text))
    return words, len(text)
