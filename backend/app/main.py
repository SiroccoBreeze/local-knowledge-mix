"""Local Knowledge API entrypoint.

Phase-1 surface: scan / documents / content / search / neighbors / assets.
Binds to 127.0.0.1 by default (personal, single-machine). When the built
frontend exists (frontend/dist), it is served here too — including the
read-only /share/{id} page (single port, no extra server).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from app.api import routes_assets, routes_docs, routes_files, routes_scan, routes_search
from app.api.models import HealthResponse, ScanReportModel
from app.config import REPO_ROOT
from app.db.engine import get_engine
from app.db.schema import ensure_schema, get_meta

_PREFIX = "/api/v1"
FE_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Schema is a derived artifact: create it eagerly so /health works before
    # the first scan ever ran.
    with get_engine().begin() as conn:
        ensure_schema(conn)
    yield


app = FastAPI(title="local-knowledge", version="0.3.0", lifespan=lifespan)
for router in (
    routes_scan.router,
    routes_docs.router,
    routes_search.router,
    routes_files.router,
    routes_assets.router,
):
    app.include_router(router, prefix=_PREFIX)


@app.exception_handler(HTTPException)
async def _http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    """统一错误信封：{"error": {"code": ..., "message": ...}}。"""
    if isinstance(exc.detail, dict):
        body = {"error": exc.detail}
    else:
        body = {"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.get(f"{_PREFIX}/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    last_scan_at: str | None = None
    report: ScanReportModel | None = None
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            last_scan_at = get_meta(conn, "last_scan_at")
            raw = get_meta(conn, "last_scan_report")
        if raw:
            report = ScanReportModel.model_validate_json(raw)
        return HealthResponse(status="ok", db="ok", last_scan_at=last_scan_at, last_scan_report=report)
    except Exception:  # noqa: BLE001 — health must never 500
        return HealthResponse(status="error", db="error", last_scan_at=last_scan_at, last_scan_report=None)


# ---- 前端静态托管（构建产物存在时启用；/share/{id} 走 SPA fallback）。
# 必须注册在 API 路由之后 —— 它是兜底路由，绝不能遮蔽 /api/*。----
if (FE_DIST / "index.html").is_file():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=FE_DIST / "assets"), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (FE_DIST / path).resolve()
        try:
            candidate.relative_to(FE_DIST.resolve())
        except ValueError:
            raise HTTPException(404) from None
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FE_DIST / "index.html")


__all__ = ["app"]
