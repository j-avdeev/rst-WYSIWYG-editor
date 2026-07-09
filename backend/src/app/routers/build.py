from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from rstkit.store import LocalGitStore

from ..build import manager_for
from ..deps import get_store

router = APIRouter()


@router.post("/api/build")
def start_build(store: LocalGitStore = Depends(get_store)) -> dict:
    return manager_for(store.root).start()


@router.get("/api/build/status")
def build_status(store: LocalGitStore = Depends(get_store)) -> dict:
    return manager_for(store.root).status()


@router.get("/built/{rel_path:path}")
def built_file(rel_path: str, store: LocalGitStore = Depends(get_store)) -> FileResponse:
    """Serves the sphinx-build output. A dynamic endpoint (not a StaticFiles
    mount) so it always follows the store root, including in tests with
    dependency overrides."""
    outdir = (store.root / "build" / "html").resolve()
    candidate = (outdir / rel_path.lstrip("/\\")).resolve()
    try:
        candidate.relative_to(outdir)
    except ValueError:
        raise HTTPException(status_code=400, detail="path escapes build output")
    if candidate.is_dir():
        candidate = candidate / "index.html"
    if not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail="not built yet — run a build first",
        )
    media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return FileResponse(candidate, media_type=media_type)
