from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rstkit.gitio import GitError, GitRepo
from rstkit.pages import PageError, add_toctree_entry, new_page_bytes, update_toctree_references
from rstkit.store import LocalGitStore, PathOutsideRootError

from ..deps import get_store
from .git import get_repo

router = APIRouter()


def _validate_rst_path(rel_path: str) -> str:
    rel = rel_path.strip().replace("\\", "/").lstrip("/")
    if not rel.lower().endswith(".rst"):
        raise HTTPException(status_code=422, detail="path must end with .rst")
    if any(seg in ("", ".", "..") for seg in rel.split("/")):
        raise HTTPException(status_code=422, detail="invalid path")
    return rel


class CreatePageRequest(BaseModel):
    path: str                 # store-relative target, must end with .rst
    title: str
    toctree_index: str | None = None  # optional index .rst to register the page in


@router.post("/api/files")
def create_page(req: CreatePageRequest, store: LocalGitStore = Depends(get_store)) -> dict:
    rel = _validate_rst_path(req.path)
    try:
        target = store.abspath(rel)
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="path escapes project root")
    if target.exists():
        raise HTTPException(status_code=409, detail="file already exists")

    try:
        data = new_page_bytes(req.title)
    except PageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    toctree_new_bytes: bytes | None = None
    if req.toctree_index:
        index_rel = _validate_rst_path(req.toctree_index)
        try:
            index_bytes = store.read_bytes(index_rel)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"toctree index not found: {index_rel}")
        try:
            toctree_new_bytes = add_toctree_entry(index_bytes, index_rel, rel)
        except PageError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    # all validation done — write both files
    target.parent.mkdir(parents=True, exist_ok=True)
    store.write_bytes(rel, data)
    if toctree_new_bytes is not None and req.toctree_index:
        store.write_bytes(_validate_rst_path(req.toctree_index), toctree_new_bytes)

    return {"path": rel, "toctree_updated": bool(toctree_new_bytes)}


class RenameRequest(BaseModel):
    path: str
    new_path: str


@router.post("/api/files/rename")
def rename_page(
    req: RenameRequest,
    store: LocalGitStore = Depends(get_store),
    repo: GitRepo = Depends(get_repo),
) -> dict:
    rel = _validate_rst_path(req.path)
    new_rel = _validate_rst_path(req.new_path)
    if rel == new_rel:
        raise HTTPException(status_code=422, detail="paths are identical")
    try:
        source = store.abspath(rel)
        target = store.abspath(new_rel)
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="path escapes project root")
    if not source.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if target.exists():
        raise HTTPException(status_code=409, detail="target already exists")

    try:
        repo.move(rel, new_rel)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # update toctree entries across the tree that pointed at the old docname
    updated: list[str] = []
    for path in sorted(store.root.rglob("*.rst")):
        if any(part.lower() in ("build", "_build", ".git") for part in path.parts):
            continue
        file_rel = path.relative_to(store.root).as_posix()
        data = path.read_bytes()
        new_bytes = update_toctree_references(data, file_rel, rel, new_rel)
        if new_bytes is not None:
            store.write_bytes(file_rel, new_bytes)
            updated.append(file_rel)

    return {"path": new_rel, "toctrees_updated": updated}
