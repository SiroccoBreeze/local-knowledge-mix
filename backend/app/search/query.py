"""Query parsing, FTS5 execution, and on-disk snippet generation.

The FTS index is contentless, so hits are rendered by reading the markdown
file from raw/ at request time (small LRU keyed by rel_path + mtime_ns).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, text

from app.config import get_settings
from app.scanner.parse import to_plain_text

_TOKEN_RE = re.compile(r'"[^"]*"|\S+')
_BAD_CHARS_RE = re.compile(r'["(){}*\\]')
_ESCAPE_LIKE_RE = re.compile(r'([\\%_])')

SEARCH_COLS = ("title", "body", "headings")


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

    Include terms are joined by implicit AND (space). Excludes are appended as
    `` NOT (...)`` — FTS5 accepts "A NOT (neg)", not "A AND NOT (neg)".
    """
    positive = [_column_clause(t) for t in terms if t.op == "include"]
    negative = ["NOT " + _column_clause(t) for t in terms if t.op == "exclude"]
    return " ".join(positive + negative)


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


def search(engine: Engine, q: str, *, limit: int = 20, offset: int = 0) -> SearchResult:
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

    cols = "d.*"
    rank = "bm25(docs_fts, 1.5, 1.0, 1.2)"
    base = (
        "FROM docs_fts JOIN documents d ON d.id = docs_fts.rowid"
        f" WHERE {where_sql}"
    )

    total = int(
        engine.connect()
        .execute(text(f"SELECT count(*) {base}"), params)
        .scalar()
    )
    rows = (
        engine.connect()
        .execute(
            text(
                f"SELECT {cols}, {rank} AS score {base}"
                f" ORDER BY score ASC, d.id ASC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        .mappings()
        .all()
    )
    include_terms = sorted({t.term for t in terms if t.op == "include"}, key=len, reverse=True)
    raw_root_str = str(get_settings().raw_root.resolve())
    hits = [
        Hit(
            doc=dict(row),
            score=round(float(row["score"]), 4),
            snippets=build_snippets(raw_root_str, row["rel_path"], row["mtime_ns"], include_terms),
        )
        for row in rows
    ]
    return SearchResult(query=q, total=total, hits=hits, limit=limit, offset=offset)


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
    raw_root: str, rel_path: str, mtime_ns: int, terms: list[str], *, window: int = 90, max_hits: int = 3
) -> list[Snippet]:
    """Read the file content, locate terms, merge windows, emit <mark> HTML."""
    plain = _plain_text(raw_root, rel_path, mtime_ns)
    if not plain or not terms:
        return []

    spans: list[tuple[int, int]] = []
    for term in terms:
        start = 0
        while True:
            idx = plain.lower().find(term.lower(), start)
            if idx < 0:
                break
            spans.append((idx, idx + len(term)))
            start = idx + 1

    merged: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1] + window:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    snippets: list[Snippet] = []
    for s, e in merged[:max_hits]:
        a, b = max(0, s - window), min(len(plain), e + window)
        start_line = plain.count("\n", 0, s) + 1
        end_line = plain.count("\n", 0, e) + 1
        display = html.escape(plain[a:b])
        for term in terms:
            if not term:
                continue
            needle = re.escape(html.escape(term))
            display = re.sub(needle, lambda m: f"<mark>{m.group(0)}</mark>", display, flags=re.IGNORECASE)
        snippets.append(Snippet(text=display, start_line=start_line, end_line=end_line))
    return snippets


__all__ = ["SearchResult", "Hit", "Snippet", "ParseTerm", "parse_query", "search", "build_snippets"]
