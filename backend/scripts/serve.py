"""CLI: serve the API.

Usage (from backend/):
    python -m scripts.serve [--host 127.0.0.1] [--port 8000]

Binds to 127.0.0.1 by default — this is a personal, single-machine service.
"""

from __future__ import annotations

import argparse

from app.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local-knowledge API")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    if args.host:
        get_settings().host = args.host
    if args.port:
        get_settings().port = args.port

    import uvicorn

    uvicorn.run("app.main:app", host=get_settings().host, port=get_settings().port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
