from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rstkit.gitio import GitError, GitRepo
from rstkit.store import LocalGitStore

from ..deps import get_store

router = APIRouter()


@lru_cache(maxsize=4)
def _repo_for(root: str) -> GitRepo:
    return GitRepo(root)


def get_repo(store: LocalGitStore = Depends(get_store)) -> GitRepo:
    try:
        return _repo_for(str(store.root))
    except GitError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/api/git/status")
def git_status(repo: GitRepo = Depends(get_repo)) -> dict:
    try:
        return repo.status().model_dump()
    except GitError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/git/diff")
def git_diff(path: str, repo: GitRepo = Depends(get_repo)) -> dict:
    try:
        return repo.diff(path)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class CommitRequest(BaseModel):
    message: str
    paths: list[str]


@router.post("/api/git/commit")
def git_commit(req: CommitRequest, repo: GitRepo = Depends(get_repo)) -> dict:
    try:
        return repo.commit(req.paths, req.message)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class DiscardRequest(BaseModel):
    path: str


@router.post("/api/git/discard")
def git_discard(req: DiscardRequest, repo: GitRepo = Depends(get_repo)) -> dict:
    try:
        repo.discard(req.path)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
