"""DocumentStore: the seam between the editor and where files actually live.

Phase 1 ships one implementation, LocalGitStore, operating on a local git
checkout via plain filesystem I/O. A future GitLab-API-backed store can
implement the same protocol without touching the parsing/serialization core
or the FastAPI routers above it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class FileEntry(BaseModel):
    path: str          # posix-style, relative to store root
    name: str
    is_dir: bool
    children: list["FileEntry"] = []


class PathOutsideRootError(Exception):
    pass


class DocumentStore(Protocol):
    root: Path

    def list_tree(self) -> FileEntry: ...
    def read_bytes(self, rel_path: str) -> bytes: ...
    def write_bytes(self, rel_path: str, data: bytes) -> None: ...
    def resolve_asset(self, doc_rel_path: str, uri: str) -> Path | None: ...


_RST_OR_DIR_SKIP = {".git", "build", "_build", "node_modules", "__pycache__"}


class LocalGitStore:
    """Reads/writes an rst tree directly on disk. `root` is the Sphinx
    source directory (contains conf.py), matching how Sphinx itself resolves
    doc-relative and srcdir-rooted (leading `/`) paths."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"store root does not exist: {self.root}")

    def _resolve(self, rel_path: str) -> Path:
        # reject absolute paths and traversal outside root
        candidate = (self.root / rel_path.lstrip("/\\")).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise PathOutsideRootError(rel_path) from None
        return candidate

    def list_tree(self) -> FileEntry:
        return self._walk(self.root)

    def _walk(self, dir_path: Path) -> FileEntry:
        rel = dir_path.relative_to(self.root).as_posix()
        entry = FileEntry(
            path="" if rel == "." else rel,
            name=dir_path.name if rel != "." else self.root.name,
            is_dir=True,
            children=[],
        )
        try:
            items = sorted(
                dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except PermissionError:
            return entry
        for item in items:
            if item.name in _RST_OR_DIR_SKIP or item.name.startswith("."):
                continue
            if item.is_dir():
                child = self._walk(item)
                if child.children:  # skip dirs with no visible content
                    entry.children.append(child)
            elif item.suffix.lower() == ".rst":
                entry.children.append(
                    FileEntry(
                        path=item.relative_to(self.root).as_posix(),
                        name=item.name,
                        is_dir=False,
                    )
                )
        return entry

    def read_bytes(self, rel_path: str) -> bytes:
        path = self._resolve(rel_path)
        return path.read_bytes()

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        path = self._resolve(rel_path)
        path.write_bytes(data)

    def resolve_asset(self, doc_rel_path: str, uri: str) -> Path | None:
        """Mirror Sphinx: a leading '/' is rooted at the source dir, else
        the path is relative to the referencing document's directory."""
        if uri.startswith("/"):
            candidate = self._resolve(uri)
        else:
            doc_dir = (self.root / doc_rel_path).parent
            candidate = (doc_dir / uri).resolve()
            try:
                candidate.relative_to(self.root)
            except ValueError:
                return None
        return candidate if candidate.is_file() else None
