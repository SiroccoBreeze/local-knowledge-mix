"""Strictly read-only directory walking for raw/.

walk_files only lists directory entries and stat()s files. It never opens
files for writing, never follows symlinks, and drops anything that would
resolve outside raw_root (symlink escape defense).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.config import IGNORED_NAMES, get_settings


@dataclass(frozen=True)
class FileInfo:
    rel_path: str  # POSIX path relative to the raw root
    abs_path: Path
    size: int
    mtime_ns: int


def walk_files(raw_root: Path) -> list[FileInfo]:
    """All in-scope document files under raw_root, sorted by rel_path.

    - Missing / non-directory raw root  -> [].
    - Hidden entries and IGNORED_NAMES (in any directory) are excluded.
    - Only files whose suffix is in get_settings().extensions are returned.
    - Symlinked files are skipped entirely (content must live inside raw/).
    - Files that resolve outside raw_root are dropped.
    """
    root = raw_root.resolve()
    if not root.is_dir():
        return []

    found: list[FileInfo] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in IGNORED_NAMES
        )
        for name in sorted(filenames):
            if name.startswith(".") or name in IGNORED_NAMES:
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() not in get_settings().extensions:
                continue
            if path.is_symlink():
                continue
            resolved = path.resolve()
            rel = _rel_under_root(resolved, root)
            if rel is None:
                continue
            st = resolved.stat()
            found.append(
                FileInfo(rel_path=rel, abs_path=resolved, size=st.st_size, mtime_ns=st.st_mtime_ns)
            )
    return sorted(found, key=lambda f: f.rel_path)


def _rel_under_root(resolved: Path, root: Path) -> str | None:
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return None
