"""Context Builder — 纯文本 Context 构造器（V0.6 Phase 12）。

RetrievalResult → 安全、稳定、可控的 AI 纯文本 Context。

设计原则：
- 只处理已进入 RetrievalResult 的数据，不重新搜索/related。
- 纯文本输出（无 HTML、无绝对路径、无 SQL、无 DB 内部路径）。
- 预算可配置（MAX_DOCUMENTS / MAX_CONTEXT_CHARS / MAX_SNIPPET_CHARS）。
- 确定性的截断，不随机丢弃。
- 合并多个 RetrievalResult 时按 document_id 去重（首次出现优先）。
"""

from __future__ import annotations

import html
import re

from app.retrieval.contract import RetrievalResult, to_context

# 默认实验参数（可通过函数参数覆盖）
MAX_CONTEXT_CHARS = 12000
MAX_DOCUMENTS = 8
MAX_SNIPPET_CHARS = 1500

# 输出安全清洗：禁止泄漏内部路径、DB、SQL、HTML/脚本
_SENSITIVE = [
    (re.compile(r'/home/[^\s,;:)]*', re.IGNORECASE), "[redacted]"),
    (re.compile(r'/Users/[^\s,;:)]*', re.IGNORECASE), "[redacted]"),
    (re.compile(r'[a-zA-Z]:\\[^\s,;:)]*'), "[redacted]"),
    (re.compile(r'/raw/[^\s,;:)]*'), "[redacted]"),
    (re.compile(r'knowledge\.db[-sha\d]*', re.IGNORECASE), "[redacted]"),
    (re.compile(r'\bSELECT\b.*?\bFROM\b', re.IGNORECASE | re.DOTALL), "[redacted]"),
    (re.compile(r'\bINSERT\s+INTO\b', re.IGNORECASE), "[redacted]"),
    (re.compile(r'\bDELETE\s+FROM\b', re.IGNORECASE), "[redacted]"),
    (re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL), "[redacted]"),
]


def _sanitize(text: str) -> str:
    """移除脚本块、HTML 标签、转义实体、红敏感路径/DB/SQL。"""
    t = re.sub(r'<script[^>]*>.*?</script>', '[redacted]', text, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    for pattern, replacement in _SENSITIVE:
        t = pattern.sub(replacement, t)
    return t


def _format_item(item, idx: int, max_snippet: int) -> str:
    """单篇文档 → [N] 格式文本块。"""
    lines = [f"[{idx}] {item.title}"]
    lines.append(f"路径：{item.rel_path}")
    lines.append(f"相关度：{item.score}")
    if item.knowledge_status is not None:
        lines.append(f"状态：{item.knowledge_status}")
    text = item.snippet_text or ""
    if text:
        if len(text) > max_snippet:
            text = text[:max_snippet] + "…"
        lines.append("")
        lines.append(text)
    lines.append("")
    return "\n".join(lines)


def _format_blocks(
    items: list,
    *,
    max_docs: int,
    max_chars: int,
    max_snippet: int,
) -> str:
    """通用格式化逻辑：多篇文档 → 预算受限的纯文本 Context。"""
    selected = items[:max_docs]
    parts: list[str] = []
    for i, item in enumerate(selected, 1):
        block = _format_item(item, i, max_snippet)
        estimated = len(block) + (sum(len(p) for p in parts) if parts else 0)
        if estimated > max_chars:
            remaining = max_chars - (sum(len(p) for p in parts) if parts else 0)
            if remaining > 0:
                truncated = block[:remaining]
                last_nl = truncated.rfind("\n", 0, remaining)
                if last_nl > 0:
                    truncated = truncated[:last_nl]
                parts.append(truncated)
            break
        parts.append(block)
    return "\n".join(parts).strip()


def build_context(
    result: RetrievalResult,
    *,
    max_docs: int = MAX_DOCUMENTS,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_snippet: int = MAX_SNIPPET_CHARS,
) -> str:
    """单个 RetrievalResult → 纯文本 Context。

    内部先经 to_context() 转为带纯文本 snippet 的 RetrievalContext，
    再 format 为 [1] 标题 / 路径 / 相关度 / 片段 结构。
    """
    ctx = to_context(result)
    if not ctx.items:
        return ""
    raw = _format_blocks(ctx.items, max_docs=max_docs, max_chars=max_chars, max_snippet=max_snippet)
    return _sanitize(raw)


def merge_contexts(
    results: list[RetrievalResult],
    *,
    max_docs: int = MAX_DOCUMENTS,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_snippet: int = MAX_SNIPPET_CHARS,
) -> str:
    """合并多个 RetrievalResult（search + related 等），document_id 去重。

    首次出现的文档优先保留（search 在前，related 在后补充）。
    """
    seen: set[int] = set()
    merged: list = []
    for result in results:
        ctx = to_context(result)
        for item in ctx.items:
            if item.document_id not in seen:
                seen.add(item.document_id)
                merged.append(item)
    if not merged:
        return ""
    raw = _format_blocks(merged, max_docs=max_docs, max_chars=max_chars, max_snippet=max_snippet)
    return _sanitize(raw)


__all__ = [
    "MAX_CONTEXT_CHARS",
    "MAX_DOCUMENTS",
    "MAX_SNIPPET_CHARS",
    "build_context",
    "merge_contexts",
]
