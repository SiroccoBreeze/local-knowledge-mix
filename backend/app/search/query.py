"""Query parsing, FTS5 execution, and on-disk snippet generation.

The FTS index is contentless, so hits are rendered by reading the markdown
file from raw/ at request time (small LRU keyed by rel_path + mtime_ns).

V0.5 检索模型（"FTS5 候选召回 + 轻量重排"，非全库精确重排）：

- keyword 模式：legacy 行为，完全保持（bm25 ASC 即原始相关度序、旧 snippet）。
- smart 模式（默认）：召回与 keyword 严格一致，仅叠加——

    1. rerank：bm25 候选内 min-max 归一化（越大越相关，0..1）
       + 可解释线性加分（标题 / headings / 短语 / 正文 / path / 标签）
       → final DESC 排序（score 越大 = 越相关）
    2. matched_terms：该文档实际命中的查询词（去重、长词优先）
    3. snippet：优先选同时覆盖多个词的窗口

权重集中在 RANK_WEIGHTS —— 实验参数，非架构规则，可随真实数据调整。
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, text

from app.config import get_settings
from app.scanner.parse import to_plain_text

_TOKEN_RE = re.compile(r'"[^"]*"|\S+')
_BAD_CHARS_RE = re.compile(r'["(){}*\\]')
_ESCAPE_LIKE_RE = re.compile(r'([\\%_])')

SEARCH_COLS = ("title", "body", "headings")

# ---- 重排权重（实验参数，可调整；标题 > 短语 > heading > 正文） ----
RANK_WEIGHTS = {
    "title": 3.0,    # 标题命中/次
    "phrase": 2.0,   # 精确短语命中/次（标题/headings/正文任一）
    "heading": 1.5,  # headings 命中/次
    "tag": 1.5,      # frontmatter 标签命中/次
    "path": 1.2,     # term 出现在 rel_path 中 /次（略高于归一化最大差，保证总能盖过）
    "body": 0.4,     # 正文命中/次（bm25 已覆盖，仅弱加权）
}
CANDIDATE_MIN = 100     # 候选集下限
CANDIDATE_MARGIN = 50   # offset+limit 之外的富余

_ADJACENCY_WINDOW = 90  # smart snippet 分词聚类窗口


@dataclass(frozen=True)
class ParseTerm:
    op: str  # "include" | "exclude"
    phrase: bool
    term: str


@dataclass(frozen=True)
class Snippet:
    text: str  # HTML, query terms wrapped in <mark>
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Hit:
    doc: dict
    score: float
    snippets: list[Snippet]
    matched_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchResult:
    query: str
    total: int
    hits: list[Hit]
    limit: int
    offset: int


def parse_query(q: str) -> list[ParseTerm]:
    """Tokenize a user query. Quoting/`-` handled; junk chars scrubbed.

    Empty terms are dropped, so `'-  ...'` yields no include terms at all.
    """
    out: list[ParseTerm] = []
    for token in _TOKEN_RE.findall(q):
        if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
            op, phrase, raw = "include", True, token[1:-1]
        elif token.startswith("-"):
            op, phrase, raw = "exclude", False, token[1:]
        else:
            op, phrase, raw = "include", False, token
        raw = _BAD_CHARS_RE.sub(" ", raw)
        raw = " ".join(raw.split())
        if raw:
            out.append(ParseTerm(op=op, phrase=phrase, term=raw))
    return out


def _column_clause(t: ParseTerm) -> str:
    if t.phrase or " " in t.term:
        conds = [f'{col}:"{t.term}"' for col in SEARCH_COLS]
    else:
        conds = [f"{col}:{t.term}" for col in SEARCH_COLS]
    return "(" + " OR ".join(conds) + ")"


def build_match(terms: list[ParseTerm]) -> str:
    """Build a safe FTS5 MATCH expression.

    Includes are joined with explicit `` AND `` (parenthesized column-OR groups
    cannot be juxtaposed / implicitly AND-ed in FTS5). Excludes are appended as
    `` NOT (...)`` — FTS5 accepts "A AND B NOT (neg)" but rejects "A AND NOT (neg)".
    """
    positive = " AND ".join(_column_clause(t) for t in terms if t.op == "include")
    negative = " ".join("NOT " + _column_clause(t) for t in terms if t.op == "exclude")
    return (positive + (" " + negative if negative else "")) if positive else negative


def _like_pattern(value: str) -> str:
    return "%" + _ESCAPE_LIKE_RE.sub(r"\\\1", value) + "%"


def short_term_filters(terms: list[ParseTerm]) -> tuple[str, dict]:
    """LIKE fallback for terms shorter than the trigram minimum (3 chars).

    Trigram cannot index <3-character tokens; those terms are instead matched
    against the *stored* metadata columns (title / headings / rel_path), never
    against the body (which lives only in the contentless FTS index).
    """
    parts: list[str] = []
    params: dict[str, str] = {}
    for i, t in enumerate(terms):
        if t.phrase or len(t.term) >= 3:
            continue
        pat = _like_pattern(t.term)
        if t.op == "include":
            parts.append(
                f"(d.title LIKE :li{i} ESCAPE '\\' OR d.headings LIKE :lh{i} ESCAPE '\\'"
                f" OR d.rel_path LIKE :lr{i} ESCAPE '\\')"
            )
        else:
            parts.append(
                f"d.title NOT LIKE :li{i} ESCAPE '\\' AND d.headings NOT LIKE :lh{i}"
                f" ESCAPE '\\' AND d.rel_path NOT LIKE :lr{i} ESCAPE '\\'"
            )
        params[f"li{i}"] = pat
        params[f"lh{i}"] = pat
        params[f"lr{i}"] = pat
    return (" AND ".join(parts), params) if parts else ("", {})


def _json_list(value: str | None) -> list:
    if not value:
        return []
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return []


def _json_dict(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def search(
    engine: Engine, q: str, *, limit: int = 20, offset: int = 0, mode: str = "smart"
) -> SearchResult:
    """FTS5 candidate retrieval + optional lightweight rerank.

    mode:
      "keyword" -> legacy behavior (bm25 ASC, old snippets, no matched_terms).
      "smart"   -> same recall; rerank / matched_terms / better snippets.
    """
    terms = parse_query(q)
    include_terms = [t for t in terms if t.op == "include"]
    if not terms or not include_terms:
        # 纯排除词 / 空查询不给整个索引（安全姿态）：至少需要一个正向关键词。
        return SearchResult(query=q, total=0, hits=[], limit=limit, offset=offset)

    like_sql, like_params = short_term_filters(terms)
    match_terms = [t for t in terms if t.phrase or len(t.term) >= 3]

    where = ["d.status NOT IN ('missing','failed')"]
    params: dict = {"limit": limit, "offset": offset, **like_params}
    if match_terms:
        where.insert(0, "docs_fts MATCH :match")
        params["match"] = build_match(terms)
    if like_sql:
        where.append(like_sql)
    where_sql = " AND ".join(where)

    base = (
        "FROM docs_fts JOIN documents d ON d.id = docs_fts.rowid"
        f" WHERE {where_sql}"
    )

    total = int(engine.connect().execute(text(f"SELECT count(*) {base}"), params).scalar())

    # 候选召回：与 keyword 完全一致的 FTS5 结果（bm25 ASC = 原始相关度），
    # 但先把候选取够（smart 需要在候选内重排后再分页）。
    candidate_limit = max(CANDIDATE_MIN, offset + limit + CANDIDATE_MARGIN)
    rows = (
        engine.connect()
        .execute(
            text(
                f"SELECT d.*, bm25(docs_fts, 1.5, 1.0, 1.2) AS bm25 {base}"
                f" ORDER BY bm25 ASC, d.id ASC LIMIT :cl"
            ),
            {**params, "cl": candidate_limit},
        )
        .mappings()
        .all()
    )
    if not rows:
        return SearchResult(query=q, total=0, hits=[], limit=limit, offset=offset)

    if mode == "keyword":
        return _keyword_result(q, total, limit, offset, rows, include_terms)

    return _smart_result(q, total, limit, offset, rows, include_terms)


def _keyword_result(q, total, limit, offset, rows, include_terms) -> SearchResult:
    selected = rows[offset : offset + limit]
    raw_root_str = str(get_settings().raw_root.resolve())
    term_strings = sorted({t.term for t in include_terms}, key=len, reverse=True)
    hits = [
        Hit(
            doc=dict(row),
            score=round(float(row["bm25"]), 4),
            snippets=build_snippets(raw_root_str, row["rel_path"], row["mtime_ns"], term_strings),
        )
        for row in selected
    ]
    return SearchResult(query=q, total=total, hits=hits, limit=limit, offset=offset)


def _smart_result(q, total, limit, offset, rows, include_terms) -> SearchResult:
    bm25s = [float(r["bm25"]) for r in rows]
    b_min, b_max = min(bm25s), max(bm25s)
    spread = b_max - b_min

    def norm_bm25(raw: float) -> float:
        """把 FTS5 原始 bm25（越小越相关）归一化为 0..1（越大越相关）。"""
        return ((b_max - raw) / spread) if spread > 0 else 1.0

    raw_root_str = str(get_settings().raw_root.resolve())
    scored: list[tuple[float, dict, list[str]]] = []
    for row in rows:
        boost, matched = _compute_boost(row, include_terms, raw_root_str)
        final = norm_bm25(float(row["bm25"])) + boost
        scored.append((final, dict(row), matched))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))

    hits: list[Hit] = []
    for final, meta, matched in scored[offset : offset + limit]:
        hits.append(
            Hit(
                doc=meta,
                score=round(final, 4),
                snippets=(
                    build_smart_snippets(raw_root_str, meta["rel_path"], meta["mtime_ns"], matched)
                    if matched
                    else []
                ),
                matched_terms=matched,
            )
        )
    return SearchResult(query=q, total=total, hits=hits, limit=limit, offset=offset)


def _compute_boost(row, include_terms, raw_root_str: str) -> tuple[float, list[str]]:
    """单个候选的行级加分与 matched_terms（可解释、确定性）。

    score = Σ W[field] × 该术语在对应字段的出现次数
    """
    load = dict(row)
    title = load.get("title") or ""
    headings_text = " ".join(h.get("text", "") for h in _json_list(load.get("headings")))
    tags = _json_dict(load.get("frontmatter")).get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags_text = " ".join(str(t) for t in tags)
    path = load.get("rel_path") or ""
    body = _plain_text(raw_root_str, path, load.get("mtime_ns") or 0)

    total_boost = 0.0
    matched: list[str] = []
    for t in include_terms:
        term = t.term
        if not term:
            continue
        title_hits = _count(title, term)
        head_hits = _count(headings_text, term)
        body_hits = _count(body, term)
        path_hits = _count(path, term)
        tag_hits = _count(tags_text, term)
        if t.phrase and " " in term:
            phrase_hits = _count(title, term) + _count(headings_text, term) + _count(body, term)
            total_boost += RANK_WEIGHTS["phrase"] * phrase_hits
        else:
            total_boost += (
                RANK_WEIGHTS["title"] * title_hits
                + RANK_WEIGHTS["heading"] * head_hits
                + RANK_WEIGHTS["body"] * body_hits
                + RANK_WEIGHTS["path"] * path_hits
                + RANK_WEIGHTS["tag"] * tag_hits
            )
        if title_hits + head_hits + body_hits + path_hits + tag_hits > 0:
            matched.append(term)
    return total_boost, sorted(matched, key=len, reverse=True)


def _count(text: str, term: str) -> int:
    return text.lower().count(term.lower()) if term else 0


@lru_cache(maxsize=64)
def _plain_text(raw_root: str, rel_path: str, mtime_ns: int) -> str:
    """Plain text of one file, cached until its mtime changes."""
    try:
        return to_plain_text(
            (Path(raw_root) / rel_path).read_text(encoding="utf-8", errors="replace")
        )
    except OSError:
        return ""


def build_snippets(
    raw_root: str, rel_path: str, mtime_ns: int, terms: list[str] | None, *, window: int = 90, max_hits: int = 3
) -> list[Snippet]:
    """Legacy snippet (keyword 模式)：按首次命中顺序合并窗口。"""
    plain = _plain_text(raw_root, rel_path, mtime_ns)
    if not plain or not terms:
        return []
    spans = _term_spans(plain, terms)
    if not spans:
        return []
    merged: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1] + window:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return _emit_snippets(plain, merged, terms, max_hits)


def build_smart_snippets(
    raw_root: str, rel_path: str, mtime_ns: int, terms: list[str], *, window: int = _ADJACENCY_WINDOW, max_hits: int = 3
) -> list[Snippet]:
    """Smart snippet：优先挑选覆盖更多不同查询词的窗口。"""
    plain = _plain_text(raw_root, rel_path, mtime_ns)
    if not plain or not terms:
        return []

    # 每个命中：起点、终点、来源 term
    hits: list[tuple[int, int, str]] = []
    for term in terms:
        start = 0
        while True:
            idx = plain.lower().find(term.lower(), start)
            if idx < 0:
                break
            hits.append((idx, idx + len(term), term))
            start = idx + 1
    if not hits:
        return []

    merged: list[list[tuple[int, int, str]]] = []
    for h in sorted(hits, key=lambda x: (x[0], x[1])):
        if merged and h[0] <= merged[-1][-1][1] + window:
            merged[-1].append(h)
        else:
            merged.append([h])
    # 聚类评分：覆盖词数优先；同词数取窗口更“紧凑”的
    scored = []
    for group in merged:
        span = (group[0][0], max(g[1] for g in group))
        distinct = len({g[2] for g in group})
        scored.append((distinct, -(span[1] - span[0]), span, group))
    scored.sort(key=lambda it: (-it[0], it[1]))

    return _emit_snippets(plain, [s[2] for s in scored[:max_hits]], terms, max_hits)


def _term_spans(plain: str, terms: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for term in terms:
        start = 0
        while True:
            idx = plain.lower().find(term.lower(), start)
            if idx < 0:
                break
            spans.append((idx, idx + len(term)))
            start = idx + 1
    return spans


def _emit_snippets(
    plain: str, spans: list[tuple[int, int]], terms: list[str], max_hits: int
) -> list[Snippet]:
    out: list[Snippet] = []
    for s, e in spans:
        a, b = max(0, s - 90), min(len(plain), e + 90)
        display = html.escape(plain[a:b])
        for term in terms:
            if not term:
                continue
            needle = re.escape(html.escape(term))
            display = re.sub(needle, lambda m: f"<mark>{m.group(0)}</mark>", display, flags=re.IGNORECASE)
        out.append(
            Snippet(
                text=display,
                start_line=plain.count("\n", 0, s) + 1,
                end_line=plain.count("\n", 0, e) + 1,
            )
        )
        if len(out) >= max_hits:
            break
    return out


__all__ = [
    "SearchResult",
    "Hit",
    "Snippet",
    "ParseTerm",
    "parse_query",
    "search",
    "build_snippets",
    "build_smart_snippets",
    "RANK_WEIGHTS",
]
