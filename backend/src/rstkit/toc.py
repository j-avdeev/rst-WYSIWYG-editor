"""Table-of-contents model: the document hierarchy as Sphinx will build it.

Walks toctree directives recursively from the master doc, resolving every
entry to its docname and display title (explicit "Title <doc>" titles win,
else the target page's first heading). Each entry carries provenance — which
file and which toctree block it lives in, and its position among that
block's entries — so the UI can edit exactly the right line later.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Any

from .pages import _entry_docname, _posix, _toctree_nodes
from .parse import parse_rst

_MASTER_RE = re.compile(r"^\s*(?:master_doc|root_doc)\s*=\s*['\"]([\w./-]+)['\"]", re.M)
_ENTRY_TITLE_RE = re.compile(r"^(.*?)\s*<([^<>]+)>\s*$")


def master_docname(srcdir: Path) -> str:
    conf = srcdir / "conf.py"
    if conf.is_file():
        m = _MASTER_RE.search(conf.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return "index"


def _first_heading_title(srcdir: Path, docname: str) -> str | None:
    path = srcdir / (docname + ".rst")
    try:
        data = path.read_bytes()
    except OSError:
        return None
    doc = parse_rst(data, docname + ".rst", check_health=False)
    for node in doc.nodes:
        if node.type == "heading":
            return str(node.attrs.get("title", "")).strip() or None
    return None


def _toctree_entries(node_raw: str, file_rel: str) -> list[dict[str, Any]]:
    """Entry lines of one toctree block, with per-entry docname/title and the
    entry's ordinal position (the index used by the reorder/remove ops)."""
    toctree_dir = posixpath.dirname(_posix(file_rel))
    entries = []
    position = 0
    for line in node_raw.splitlines()[1:]:
        stripped = line.strip()
        docname = _entry_docname(line, toctree_dir)
        if docname is None:
            continue
        m = _ENTRY_TITLE_RE.match(stripped)
        explicit_title = m.group(1).strip() if m else None
        entries.append(
            {
                "docname": docname,
                "explicit_title": explicit_title,
                "position": position,
            }
        )
        position += 1
    return entries


def build_toc(srcdir: Path) -> dict[str, Any]:
    srcdir = Path(srcdir)
    master = master_docname(srcdir)
    visited: set[str] = set()

    def walk(docname: str) -> list[dict[str, Any]]:
        """Children of `docname` across all its toctree blocks, in order."""
        path = srcdir / (docname + ".rst")
        try:
            data = path.read_bytes()
        except OSError:
            return []
        doc = parse_rst(data, docname + ".rst", check_health=False)
        children: list[dict[str, Any]] = []
        for ti, node in enumerate(_toctree_nodes(doc.nodes)):
            for entry in _toctree_entries(node.raw_source, docname + ".rst"):
                child_doc = entry["docname"]
                missing = not (srcdir / (child_doc + ".rst")).is_file()
                cycle = child_doc in visited
                if not missing and not cycle:
                    visited.add(child_doc)
                title = (
                    entry["explicit_title"]
                    or (None if missing else _first_heading_title(srcdir, child_doc))
                    or child_doc
                )
                children.append(
                    {
                        "docname": child_doc,
                        "path": child_doc + ".rst",
                        "title": title,
                        "missing": missing,
                        "source": {
                            "file": docname + ".rst",
                            "toctree_index": ti,
                            "position": entry["position"],
                        },
                        "children": [] if (missing or cycle) else walk(child_doc),
                    }
                )
        return children

    visited.add(master)
    tree = {
        "docname": master,
        "path": master + ".rst",
        "title": _first_heading_title(srcdir, master) or master,
        "missing": not (srcdir / (master + ".rst")).is_file(),
        "source": None,
        "children": walk(master),
    }

    skip_dirs = {"build", "_build", ".git", "node_modules", "__pycache__"}
    orphans = []
    for path in sorted(srcdir.rglob("*.rst")):
        if any(part.lower() in skip_dirs for part in path.parts):
            continue
        docname = path.relative_to(srcdir).as_posix()[: -len(".rst")]
        if docname not in visited:
            orphans.append(
                {
                    "docname": docname,
                    "path": docname + ".rst",
                    "title": _first_heading_title(srcdir, docname) or docname,
                }
            )

    return {"master": master, "tree": tree, "orphans": orphans}
