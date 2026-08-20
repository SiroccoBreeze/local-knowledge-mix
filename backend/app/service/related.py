"""Related documents — explainable composite relevance (no embeddings, no vectors).

候选集先收窄（同目录 / 共享标签 / 显式链接 / FTS 命中 / 正文 gram 命中），
再对候选计算加权相似度。复杂度 O(N)（预建指纹表 + 单遍扫描），非 O(N²) 两两对比。

RELATED_WEIGHTS 为 V0.5 实验参数，非永久架构规则 —— 依据真实 138 篇数据校准：
- tags 高度偏斜（HIS×80/医保×47）→ 单标签权重压低、总加成封顶；
- 目录宽泛（questions×96）→ 仅作弱信号；
- 显式解析链接集中在极少数文档 → 权重中等、命中稀少；
- title / heading / body 的 3-gram 指纹经“全局 df 去噪”后为最强信号。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, text

from app.config import get_settings
from app.scanner.parse import extract_frontmatter, to_plain_text


def _body_plain_text(text: str) -> str:
    """正文明文：先剥离 frontmatter，再做 markdown 标记清理。"""
    body, _meta, _err = extract_frontmatter(text)
    return to_plain_text(body)


@lru_cache(maxsize=128)
def _plain_text(raw_root: str, rel_path: str, mtime_ns: int) -> str:
    try:
        return _body_plain_text(
            (Path(raw_root) / rel_path).read_text(encoding="utf-8", errors="replace")
        )
    except OSError:
        return ""


RELATED_WEIGHTS = {
    "linked": 1.2,             # 显式解析链接（A→B 或 B→A，wiki/relative；url 无效）
    "same_directory": 0.6,     # 同目录弱信号
    "shared_tag": 0.4,         # 每个共享标签；总加成封顶 RELATED_TAG_CAP
    "title_similarity": 1.0,   # 标题 3-gram 重合比例
    "heading_similarity": 0.8, # headings 3-gram 重合比例（df 去噪后）
    "term_similarity": 0.9,    # 正文 3-gram 重合比例（df 去噪、锚点≥2 次）
}
RELATED_TAG_CAP = 0.8
RELATED_MIN_SCORE = 0.25
REASON_ORDER = (
    "linked",
    "same_directory",
    "shared_tag",
    "title_similarity",
    "heading_similarity",
    "term_similarity",
)

_CJK_RUN = re.compile(r"[一-鿿]{3,}")


def _grams(text: str, size: int = 3) -> Counter:
    out: Counter = Counter()
    for run in _CJK_RUN.findall(text or ""):
        for i in range(len(run) - size + 1):
            out[run[i : i + size]] += 1
    return out


def _json(value: str | None, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _ratio(shared: int, a_total: int, b_total: int) -> float:
    denom = min(a_total, b_total)
    return (shared / denom) if denom else 0.0


def _dir_of(rel_path: str) -> str:
    return rel_path.split("/")[0] if "/" in rel_path else ""


def find_related(engine: Engine, document_id: int, *, limit: int = 10) -> dict:
    """计算 document_id 的相关文档（仅 status='indexed'）。

    返回 {"document_id", "items":[{doc_id,title,rel_path,score,reasons}]}，score DESC。
    document_id 不存在 → 抛 DocNotFoundError。
    """
    from app.service.docs import DocNotFoundError

    with engine.connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT id, rel_path, title, frontmatter, headings, mtime_ns FROM documents"
                    " WHERE status='indexed'"
                )
            ).mappings()
        ]
        link_rows = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT from_doc, to_doc, kind FROM links"
                    " WHERE kind != 'url' AND to_doc IS NOT NULL"
                )
            ).mappings()
        ]

    anchor = next((r for r in rows if r["id"] == document_id), None)
    if anchor is None:
        raise DocNotFoundError(f"文档 {document_id} 不存在")

    raw_root = str(get_settings().raw_root.resolve())
    # ---- 预建：每篇文档的指纹与字段 ----
    docs: list[dict] = []
    for r in rows:
        fm = _json(r["frontmatter"], {}) or {}
        tags = fm.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        heading_text = " ".join(h.get("text", "") for h in _json(r["headings"], []))
        docs.append(
            {
                "row": r,
                "title": r["title"] or "",
                "tags": [str(t) for t in tags],
                "dir": _dir_of(r["rel_path"]),
                "heading_text": heading_text,
                "title_grams": _grams(r["title"] or ""),
                "heading_grams": _grams(heading_text),
                "body_grams": _grams(_plain_text(raw_root, r["rel_path"], r["mtime_ns"])),
            }
        )

    # ---- 全局 df 去噪：出现 ≥ n 篇文档的 gram 视为模板噪声 ----
    n = max(3, round(len(docs) * 0.1))
    title_df: Counter = Counter()
    head_df: Counter = Counter()
    body_df: Counter = Counter()
    for d in docs:
        # df 按“文档频次”统计（同一文档内多次出现只计一次），避免高频词被自身放大
        title_df.update(d["title_grams"].keys())
        head_df.update(d["heading_grams"].keys())
        body_df.update(d["body_grams"].keys())
    noise = {
        g
        for g, c in title_df.items()
        if c >= n
    } | {
        g
        for g, c in head_df.items()
        if c >= n
    } | {
        g
        for g, c in body_df.items()
        if c >= n
    }

    # ---- 锚点信号 ----
    a = next(d for d in docs if d["row"]["id"] == document_id)
    a_title = {k: v for k, v in a["title_grams"].items() if k not in noise}
    a_head = {k: v for k, v in a["heading_grams"].items() if k not in noise}
    a_body = {k: v for k, v in a["body_grams"].items() if k not in noise and v >= 2}

    # ---- 显式链接映射（双向，排除 url/断链） ----
    linked_ids: set[int] = set()
    for lnk in link_rows:
        if lnk["from_doc"] == document_id and lnk["to_doc"] is not None:
            linked_ids.add(lnk["to_doc"])
        elif lnk["to_doc"] == document_id:
            linked_ids.add(lnk["from_doc"])

    # ---- 单遍打分 ----
    items: list[dict] = []
    for d in docs:
        if d["row"]["id"] == document_id:
            continue
        score = 0.0
        reasons: list[str] = []

        if d["row"]["id"] in linked_ids:
            score += RELATED_WEIGHTS["linked"]
            reasons.append("linked")
        if d["dir"] == a["dir"]:
            score += RELATED_WEIGHTS["same_directory"]
            reasons.append("same_directory")

        shared_tags = len(set(d["tags"]) & set(a["tags"]))
        tag_value = min(RELATED_TAG_CAP, RELATED_WEIGHTS["shared_tag"] * shared_tags)
        if shared_tags and tag_value >= 0.05:
            score += tag_value
            reasons.append("shared_tag")

        shared_title = sum(
            min(a_title.get(k, 0), d["title_grams"].get(k, 0))
            for k in set(a_title) & set(d["title_grams"])
        )
        title_value = RELATED_WEIGHTS["title_similarity"] * _ratio(
            shared_title, sum(a_title.values()), sum(d["title_grams"].values())
        )
        if title_value >= 0.05:
            score += title_value
            reasons.append("title_similarity")

        shared_head = sum(
            min(a_head.get(k, 0), d["heading_grams"].get(k, 0))
            for k in set(a_head) & set(d["heading_grams"])
        )
        head_value = RELATED_WEIGHTS["heading_similarity"] * _ratio(
            shared_head, sum(a_head.values()), sum(d["heading_grams"].values())
        )
        if head_value >= 0.05:
            score += head_value
            reasons.append("heading_similarity")

        shared_body = sum(
            min(a_body.get(k, 0), d["body_grams"].get(k, 0))
            for k in set(a_body) & set(d["body_grams"])
        )
        body_value = RELATED_WEIGHTS["term_similarity"] * _ratio(
            shared_body, sum(a_body.values()), sum(d["body_grams"].values())
        )
        if body_value >= 0.05:
            score += body_value
            reasons.append("term_similarity")

        if score >= RELATED_MIN_SCORE:
            items.append(
                {
                    "doc_id": d["row"]["id"],
                    "title": d["title"],
                    "rel_path": d["row"]["rel_path"],
                    "score": round(score, 4),
                    "reasons": [r for r in REASON_ORDER if r in reasons],
                }
            )

    items.sort(key=lambda it: (-it["score"], it["doc_id"]))
    return {"document_id": document_id, "items": items[:limit]}


__all__ = ["RELATED_WEIGHTS", "RELATED_MIN_SCORE", "find_related"]
