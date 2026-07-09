from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rstkit.pages import (
    PageError,
    add_toctree_entry,
    remove_toctree_entry,
    reorder_toctree_entry,
)
from rstkit.store import LocalGitStore
from rstkit.toc import build_toc

from ..deps import get_store

router = APIRouter()


@router.get("/api/toc")
def get_toc(store: LocalGitStore = Depends(get_store)) -> dict:
    return build_toc(store.root)


class ReorderRequest(BaseModel):
    file: str            # file containing the toctree, store-relative
    toctree_index: int
    from_pos: int
    to_pos: int


@router.post("/api/toc/reorder")
def toc_reorder(req: ReorderRequest, store: LocalGitStore = Depends(get_store)) -> dict:
    try:
        data = store.read_bytes(req.file)
        new_bytes = reorder_toctree_entry(
            data, req.file, req.toctree_index, req.from_pos, req.to_pos
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    except PageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    store.write_bytes(req.file, new_bytes)
    return build_toc(store.root)


class RemoveRequest(BaseModel):
    file: str
    toctree_index: int
    position: int


@router.post("/api/toc/remove")
def toc_remove(req: RemoveRequest, store: LocalGitStore = Depends(get_store)) -> dict:
    try:
        data = store.read_bytes(req.file)
        new_bytes = remove_toctree_entry(data, req.file, req.toctree_index, req.position)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    except PageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    store.write_bytes(req.file, new_bytes)
    return build_toc(store.root)


class AddEntryRequest(BaseModel):
    index_file: str      # file whose (first) toctree gets the entry
    doc_path: str        # existing page to register, store-relative .rst


@router.post("/api/toc/entry")
def toc_add_entry(req: AddEntryRequest, store: LocalGitStore = Depends(get_store)) -> dict:
    try:
        if not store.abspath(req.doc_path).is_file():
            raise HTTPException(status_code=404, detail=f"page not found: {req.doc_path}")
        data = store.read_bytes(req.index_file)
        new_bytes = add_toctree_entry(data, req.index_file, req.doc_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="toctree file not found")
    except PageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    store.write_bytes(req.index_file, new_bytes)
    return build_toc(store.root)
