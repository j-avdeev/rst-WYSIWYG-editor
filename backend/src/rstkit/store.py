"""DocumentStore: the seam between the editor and where files actually live.

Phase 1 ships one implementation, LocalGitStore, operating on a local git
checkout via plain filesystem I/O. A future GitLab-API-backed store can
implement the same protocol without touching the parsing/serialization core
or the FastAPI routers above it.
"""

from __future__ import annotations

import re
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
    def write_asset(self, doc_rel_path: str, filename: str, data: bytes) -> str: ...


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

    def mtime_ns(self, rel_path: str) -> int:
        return self._resolve(rel_path).stat().st_mtime_ns

    def abspath(self, rel_path: str) -> Path:
        return self._resolve(rel_path)

    def write_asset(self, doc_rel_path: str, filename: str, data: bytes) -> str:
        """Save an uploaded image next to `doc_rel_path`, in a `media/`
        subdirectory (the convention already used throughout the corpus —
        see preprocessor.rst, methods_of_pradis.rst). Returns the URI to use
        in a `.. figure::`/`.. image::` directive, relative to the doc.
        Collisions get a numeric suffix rather than overwriting."""
        safe_name = re.sub(r"[^\w.\-]+", "_", filename).lstrip(".") or "image"
        doc_dir = self._resolve(doc_rel_path).parent
        media_dir = doc_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        stem, dot, ext = safe_name.rpartition(".")
        stem, ext = (stem, "." + ext) if dot else (safe_name, "")
        candidate = media_dir / safe_name
        n = 1
        while candidate.exists():
            candidate = media_dir / f"{stem}_{n}{ext}"
            n += 1

        candidate.write_bytes(data)
        return f"media/{candidate.name}"

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
