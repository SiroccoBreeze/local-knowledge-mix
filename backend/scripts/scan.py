"""CLI: index raw/ into data/knowledge.db.

Usage (from backend/):
    python -m scripts.scan              # incremental (fast path)
    python -m scripts.scan --full       # re-hash everything + rebuild FTS index
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan raw/ into the SQLite index")
    parser.add_argument("--full", action="store_true", help="force full re-hash + FTS rebuild")
    parser.add_argument("--raw", type=Path, default=None, help="override raw/ root")
    parser.add_argument("--db", type=Path, default=None, help="override database path")
    args = parser.parse_args()

    if args.raw:
        get_settings().raw_root = args.raw
    if args.db:
        get_settings().db_path = args.db

    from app.db.engine import get_engine
    from app.scanner import run_scan

    report = run_scan(get_engine(), full=args.full)
    data = asdict(report)
    print(f"scan complete (raw root: {data['raw_root']})")
    for key in ("added", "changed", "unchanged", "skipped", "missing", "failed"):
        print(f"  {key:<10} {data[key]}")
    print(f"  total_docs {data['total_docs']}  duration {data['duration_ms']} ms")
    if not sys.stdout.isatty():
        print(json.dumps(data, ensure_ascii=False))
    return 0 if data["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
