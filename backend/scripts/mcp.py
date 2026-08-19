"""CLI：以 stdio 启动 MCP Server（无需启动 Web 服务）。

Usage (from backend/):
    .venv/bin/python -m scripts.mcp

MCP 客户端配置指向此命令即可（见 README「MCP Client 配置」）。
"""

from __future__ import annotations

from app.mcp.server import make_server


def main() -> int:
    server = make_server()
    server.run()  # stdio 默认传输
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
