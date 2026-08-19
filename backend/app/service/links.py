"""Link/neighbors queries（REST 与 MCP 共用）。"""

from __future__ import annotations

from sqlalchemy import Engine, text

from app.service.docs import fetch_doc_row


def get_neighbors(engine: Engine, doc_id: int, *, include_broken: bool = False) -> dict:
    """进出链。

    include_broken=False（REST /neighbors）：只返回已解析的文档链接。
    include_broken=True（MCP）：出链包含断链（to_doc=NULL）与外链（kind=url）。
    """
    with engine.connect() as conn:
        if fetch_doc_row(engine, doc_id) is None:
            raise KeyError(f"文档 {doc_id} 不存在")

        if include_broken:
            outgoing = conn.execute(
                text(
                    "SELECT l.target, l.kind, l.to_doc, d.id AS doc_id,"
                    " d.rel_path, d.title FROM links l"
                    " LEFT JOIN documents d ON d.id = l.to_doc"
                    " WHERE l.from_doc = :id ORDER BY l.target"
                ),
                {"id": doc_id},
            ).mappings().all()
        else:
            outgoing = conn.execute(
                text(
                    "SELECT d.id AS doc_id, d.rel_path, d.title, l.target, l.kind"
                    " FROM links l JOIN documents d ON d.id = l.to_doc"
                    " WHERE l.from_doc = :id AND l.to_doc IS NOT NULL"
                    " ORDER BY d.rel_path"
                ),
                {"id": doc_id},
            ).mappings().all()
        incoming = conn.execute(
            text(
                "SELECT d.id AS doc_id, d.rel_path, d.title, l.target, l.kind"
                " FROM links l JOIN documents d ON d.id = l.from_doc"
                " WHERE l.to_doc = :id ORDER BY d.rel_path"
            ),
            {"id": doc_id},
        ).mappings().all()
    return {
        "outgoing": [dict(r) for r in outgoing],
        "incoming": [dict(r) for r in incoming],
    }


__all__ = ["get_neighbors"]
