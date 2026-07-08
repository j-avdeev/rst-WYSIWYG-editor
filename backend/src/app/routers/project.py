from __future__ import annotations

from fastapi import APIRouter, Depends

from rstkit.store import LocalGitStore

from ..deps import get_store

router = APIRouter()


@router.get("/api/project")
def get_project(store: LocalGitStore = Depends(get_store)) -> dict:
    return {"root": str(store.root), "name": store.root.name}
