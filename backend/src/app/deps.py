"""Process-lifetime singletons (the store is cheap; recreated only if the
root ever needs to change, which Phase 1 doesn't support via the API)."""

from __future__ import annotations

from functools import lru_cache

from rstkit.store import LocalGitStore

from .config import get_root


@lru_cache(maxsize=1)
def get_store() -> LocalGitStore:
    return LocalGitStore(get_root())
