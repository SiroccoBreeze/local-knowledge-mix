"""Document metadata + body reads (raw/ is the only source of content)."""

from __future__ import annotations

import json

from sqlalchemy import Engine, text

from app.service.files import read_raw_bytes


class DocNotFoundError(Exception):
    pass


def fetch_doc_row(engine: Engine, doc_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM documents WHERE id = :id"), {"id": doc_id}
        ).mappings().first()
        return dict(row) if row else None


def list_documents(
    engine: Engine,
    *,
    directory: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """与 REST /documents 完全一致的过滤与排序。"""
    conds: list[str] = []
    params: dict = {}
    if directory:
        conds.append("rel_path LIKE :dir ESCAPE '\\'")
        params["dir"] = "%" + directory.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/" + "%"
    if status:
        conds.append("status = :status")
        params["status"] = status
    if q:
        conds.append("(title LIKE :t ESCAPE '\\' OR rel_path LIKE :p ESCAPE '\\')")
        params["t"] = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params["p"] = params["t"]
    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    with engine.connect() as conn:
        total = int(conn.execute(text(f"SELECT count(*) FROM documents{where}"), params).scalar())
        rows = conn.execute(
            text(f"SELECT * FROM documents{where} ORDER BY rel_path ASC LIMIT :l OFFSET :o"),
            {**params, "l": limit, "o": offset},
        ).mappings().all()
    return [dict(r) for r in rows], total


def parse_doc_meta(row: dict) -> dict:
    """行 → 可直接 JSON 化的元数据（frontmatter/headings 已解析）。"""
    out = dict(row)
    fm = out.pop("frontmatter", None)
    hd = out.pop("headings", None)
    out["frontmatter"] = json.loads(fm) if fm else None
    out["headings"] = json.loads(hd) if hd else []
    return out


def read_document(engine: Engine, doc_id: int) -> dict:
    """文档全文读取：元数据来自索引，正文永远从 raw/ 文件读。"""
    row = fetch_doc_row(engine, doc_id)
    if row is None:
        raise DocNotFoundError(f"文档 {doc_id} 不存在")
    meta = parse_doc_meta(row)
    meta["content"] = read_raw_bytes(row["rel_path"]).decode("utf-8", errors="replace")
    return meta


__all__ = ["DocNotFoundError", "fetch_doc_row", "list_documents", "read_document", "parse_doc_meta"]
