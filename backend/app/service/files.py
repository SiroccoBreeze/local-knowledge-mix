"""Service layer: shared read-only logic for REST API and MCP tools.

MCP 复用这里的能力，而不是重新实现 —— 全项目对 raw/ 的文件读取
只有这一个校验点（防止路径穿越/目录行为/隐藏文件）。
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def raw_path_for(rel_path: str) -> Path | None:
    """把 raw-relative 路径解析为真实路径；任何逃逸/绝对/隐藏路径 → None。"""
    if any(p in ("", ".", "..") or p.startswith((".", "~")) for p in rel_path.split("/")):
        return None
    root = get_settings().raw_root.resolve()
    try:
        candidate = (root / rel_path).resolve(strict=False)
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def read_raw_bytes(rel_path: str) -> bytes:
    """读取 raw/ 下的文件；路径非法或不存在 → FileNotFoundError。"""
    path = raw_path_for(rel_path)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"raw/ 下不存在该文件: {rel_path}")
    return path.read_bytes()


__all__ = ["raw_path_for", "read_raw_bytes"]
