"""MCP Server（stdio 默认传输）。

Read-only Knowledge Access：让 Claude Desktop / Claude Code / Cursor 等
客户端安全地检索并读取本地 Markdown 知识库。

原则：
- raw/ 唯一可信源，只读；SQLite 只是派生索引。
- 所有工具复用 service/search/scanner 已有能力，不重新实现。
- 只有本文声明的 6 个工具；无任意文件读取、不暴露 DB/环境变量。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from sqlalchemy import Engine

from app.db.engine import get_engine
from app.mcp import tools

SERVER_NAME = "local-knowledge"


def make_server(engine: Engine | None = None) -> FastMCP:
    """构造并注册 6 个只读工具。

    engine 默认 None → 使用 config 的默认引擎（与 Web/Scanner 同一 data/knowledge.db）。
    """
    provider = (lambda: engine) if engine is not None else get_engine
    server = FastMCP(SERVER_NAME)

    @server.tool(description="全文检索知识库（FTS5 + V0.5 智能重排）。返回命中文档、分数（越大越相关）、matched_terms 与行号定位的纯文本片段。")
    def search_documents(
        query: str,
        limit: int = 20,
        offset: int = 0,
        search_mode: str = "smart",
    ) -> dict:
        return tools.search_documents_tool(
            provider(), query, limit=limit, offset=offset, search_mode=search_mode
        )

    @server.tool(description="读取一篇文档的元数据与全文（正文实时从 raw/ 文件读取，不取缓存/副本）。")
    def get_document(document_id: int) -> dict:
        return tools.get_document_tool(provider(), document_id)

    @server.tool(description="文档列表：支持标题/路径关键字、目录、状态过滤与分页。")
    def list_documents(
        q: str | None = None,
        dir: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        return tools.list_documents_tool(
            provider(), q=q, dir=dir, status=status, limit=limit, offset=offset
        )

    @server.tool(description="文档的进出链接：出链含断链标记（broken）与外链标记（external）。")
    def get_document_links(document_id: int) -> dict:
        return tools.get_document_links_tool(provider(), document_id)

    @server.tool(description="文档引用的资产（图片/附件）元数据索引。")
    def get_document_assets(document_id: int) -> dict:
        return tools.get_document_assets_tool(provider(), document_id)

    @server.tool(description="相关文档：可解释综合相关性（同目录/共享标签/标题/标题结构/正文词/显式链接），与『显式链接』区分。")
    def find_related_documents(document_id: int, limit: int = 10) -> dict:
        return tools.find_related_documents_tool(provider(), document_id, limit=limit)

    @server.tool(description="知识库整体统计：文档/资产/链接数、索引与缺失数、最近扫描时间。")
    def get_knowledge_stats() -> dict:
        return tools.get_knowledge_stats_tool(provider())

    return server


__all__ = ["make_server", "SERVER_NAME"]
