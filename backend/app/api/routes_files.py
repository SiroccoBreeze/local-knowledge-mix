"""Read-only media access under raw/ for the knowledge viewer.

Security model:
- Never lists a directory and never serves raw markdown here — document
  bodies have their own dedicated endpoint (/documents/{id}/content).
- Every request is normalized and must resolve *strictly inside* raw_root
  (defense against ``..`` / absolute / symlink-escape paths).
- Only a fixed allowlist of media suffixes is served; everything else is
  refused with 403/404, so this endpoint cannot be used to exfiltrate
  arbitrary files.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.models import ErrorBody
from app.config import get_settings

router = APIRouter(tags=["files"], prefix="/raw")

MEDIA_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".ico", ".svg"}
)

_FILE_NOT_FOUND = ErrorBody(code="FILE_NOT_FOUND", message="raw/ 下不存在该文件").model_dump()
_FILE_TYPE_NOT_ALLOWED = ErrorBody(
    code="FILE_TYPE_NOT_ALLOWED", message="该文件类型不允许通过此接口读取"
).model_dump()
INVALID_PATH = ErrorBody(code="INVALID_PATH", message="非法路径，拒绝读取").model_dump()


@router.get("/{rel_path:path}")
def raw_file(rel_path: str):
    """Serve one media file that lives under raw/.

    rel_path mirrors the document's own relative reference, e.g.
    ``assets/images/x.png``. The browser must resolve image src as a component
    of THIS path (doc dir + relative src); passing an absolute filesystem path
    or ``..``-containing path is always refused.
    """
    if _unsafe_components(rel_path):
        raise HTTPException(404, detail=_FILE_NOT_FOUND)

    root = get_settings().raw_root.resolve()
    candidate = (root / rel_path).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(404, detail=_FILE_NOT_FOUND) from None

    if not candidate.is_file():
        raise HTTPException(404, detail=_FILE_NOT_FOUND)
    if candidate.suffix.lower() not in MEDIA_SUFFIXES:
        raise HTTPException(403, detail=_FILE_TYPE_NOT_ALLOWED)

    media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return FileResponse(
        candidate,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _unsafe_components(rel_path: str) -> bool:
    """Reject dot/empty/'..'/~ segments before touching the filesystem."""
    return any(part in ("", ".", "..") or part.startswith((".", "~")) for part in rel_path.split("/"))


__all__ = ["router"]
