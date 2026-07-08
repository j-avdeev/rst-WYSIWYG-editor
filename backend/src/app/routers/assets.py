from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from rstkit.store import LocalGitStore, PathOutsideRootError

from ..deps import get_store

router = APIRouter()


@router.get("/api/asset")
def get_asset(
    doc: str, uri: str, store: LocalGitStore = Depends(get_store)
) -> FileResponse:
    try:
        path = store.resolve_asset(doc, uri)
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="asset path escapes project root")
    if path is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path)
