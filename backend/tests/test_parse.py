"""Unit tests for the read-only markdown parser."""

from __future__ import annotations

from app.scanner.parse import (
    extract_frontmatter,
    extract_links,
    parse_markdown,
    title_of,
    to_plain_text,
)


def test_frontmatter_parsed():
    body, meta, err = extract_frontmatter("---\ntitle: 你好\ntags: [a, b]\n---\n正文")
    assert meta == {"title": "你好", "tags": ["a", "b"]}
    assert err is None
    assert body == "正文"


def test_no_frontmatter():
    body, meta, err = extract_frontmatter("纯正文，无 YAML 段。")
    assert meta is None
    assert err is None
    assert body == "纯正文，无 YAML 段。"


def test_broken_frontmatter_keeps_content():
    text = "---\ntitle: [未闭合\n---\n正文还能用。"
    body, meta, err = extract_frontmatter(text)
    assert meta is None
    assert err is not None and "frontmatter" in err
    assert body == text  # 内容永不丢失


def test_frontmatter_missing_closing_fence():
    text = "---\ntitle: hi\n更多正文"
    _, meta, err = extract_frontmatter(text)
    assert meta is None
    assert err is not None


def test_frontmatter_non_mapping():
    text = "---\n- a\n- b\n---\n正文"
    _, meta, err = extract_frontmatter(text)
    assert meta is None
    assert err is not None


def test_title_precedence():
    headings = [{"level": 1, "text": "H1 标题"}]
    assert title_of({"title": "元数据标题"}, headings, "x.md") == "元数据标题"
    assert title_of({"title": "  "}, headings, "x.md") == "H1 标题"
    assert title_of(None, headings, "x.md") == "H1 标题"
    assert title_of(None, [], "path/无标题文件.md") == "无标题文件"


def test_headings_and_plain_text():
    md = "# 标题A\n## 标题B\n\n正文 **粗体** [链接](https://x.edu/a) ![图](../pic.png)\n\n```py\nprint('x')\n```\n"
    pd = parse_markdown(md, "a.md")
    assert [h["text"] for h in pd.headings] == ["标题A", "标题B"]
    assert pd.title == "标题A"
    plain = pd.plain_text
    assert "标题A" in plain
    assert "粗体" in plain
    assert "https://x.edu/a" in plain  # URL 保持可检索
    assert "print('x')" in plain  # 代码块原文保持
    assert "#" not in plain.replace("print('x')", "")


def test_links_extraction():
    text = (
        "[[目标]] 与 [[别名|别名]]\n"
        "[相对](../notes/其他.md)\n"
        "[外部](https://a.b/c)\n"
        "相对锚 [节](../notes/x.md#小节)\n"
        "图片 ![img](../assets/pic.png)\n"
    )
    links = extract_links(text)
    assert ("wiki", "目标") in links
    assert ("wiki", "别名") in links
    assert ("relative", "../notes/其他.md") in links
    assert ("relative", "../notes/x.md") in links
    assert ("url", "https://a.b/c") in links
    assert not any(k == "relative" and t == "../assets/pic.png" for k, t in links)


def test_to_plain_text_markers_stripped():
    md = "> 引用\n- 列表项\n1. 有序项\n\n~~删除~~ **加粗** *斜体*\n\n---\n\n[^1] 是标注\n"
    plain = to_plain_text(md)
    assert "引用" in plain
    assert "列表项" in plain
    assert "有序项" in plain
    assert "删除" in plain and "~~" not in plain
    assert "*" not in plain
    assert "---" not in plain
    assert "是标注" in plain and "[^1]" not in plain


def test_special_characters_no_crash():
    md = "特殊字符：→ 箭头、café、emoji 🔥、<tag>、\"引号\"、a_b_c、50%+。\n"
    pd = parse_markdown(md, "s.md")
    assert pd.scan_error is None
    assert "café" in pd.plain_text
    assert pd.word_count > 0


def test_empty_document():
    pd = parse_markdown("", "empty.md")
    assert pd.title == "empty"
    assert pd.plain_text == ""
    assert pd.word_count == 0
    assert pd.headings == []
    assert pd.scan_error is None


def test_bom_tolerated():
    pd = parse_markdown("\ufeff# 有 BOM 的文档\n正文。\n", "bom.md")
    assert pd.title == "有 BOM 的文档"
    assert "正文" in pd.plain_text


def test_image_only_document():
    pd = parse_markdown("![仅图片](../img/1.png)\n", "img.md")
    assert pd.plain_text != ""
    assert pd.links == []  # 非 .md 目标不构成文档链接


def test_document_with_crlf():
    text = "---\r\ntitle: CRLF 文档\r\n---\r\n# 标题\r\n正文。\r\n"
    pd = parse_markdown(text, "crlf.md")
    assert pd.title == "CRLF 文档"
    assert [h["text"] for h in pd.headings] == ["标题"]
