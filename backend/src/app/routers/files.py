from __future__ import annotations

from fastapi import APIRouter, Depends

from rstkit.store import FileEntry, LocalGitStore

from ..deps import get_store

router = APIRouter()


@router.get("/api/files", response_model=FileEntry)
def get_file_tree(store: LocalGitStore = Depends(get_store)) -> FileEntry:
    return store.list_tree()
