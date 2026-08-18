"""Scan trigger and status endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine, text

from app.api.deps import get_engine_dep
from app.api.models import ScanReportModel
from app.db.schema import get_meta
from app.scanner import run_scan as run_scan_func

router = APIRouter(tags=["scan"])


class ScanRequest(BaseModel):
    full: bool = False


class ScanStatus(BaseModel):
    last_scan_at: str | None
    last_scan_report: ScanReportModel | None


@router.post("/scan", response_model=ScanReportModel)
def trigger_scan(
    body: ScanRequest,
    engine: Engine = Depends(get_engine_dep),
) -> ScanReportModel:
    report = run_scan_func(engine, full=body.full)
    return ScanReportModel(**asdict(report))


@router.get("/scan/status", response_model=ScanStatus)
def scan_status(engine: Engine = Depends(get_engine_dep)) -> ScanStatus:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        last_at = get_meta(conn, "last_scan_at")
        raw = get_meta(conn, "last_scan_report")
    report = ScanReportModel.model_validate_json(raw) if raw else None
    return ScanStatus(last_scan_at=last_at, last_scan_report=report)


__all__ = ["router"]
