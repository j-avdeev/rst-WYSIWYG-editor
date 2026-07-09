"""Page creation and toctree maintenance.

Toctree edits follow the same fidelity discipline as everything else: the
target file is parsed into span blocks, ONLY the toctree directive block's
raw_source is rewritten (entry appended / docname replaced in place), and
the file is reassembled by concatenating every other block verbatim.
"""

from __future__ import annotations

import posixpath
import re
from typing import Iterable

from .model import EdNode
from .parse import parse_rst

_EOL = {"crlf": "\r\n", "lf": "\n", "mixed": "\r\n", "none": "\r\n"}

_OPTION_LINE = re.compile(r"^\s*:[\w-]+:")
# a toctree entry is "docname" or "Title <docname>"
_ENTRY_TARGET = re.compile(r"<([^<>]+)>\s*$")


class PageError(Exception):
    pass


def new_page_bytes(title: str) -> bytes:
    title = title.strip()
    if not title:
        raise PageError("title is required")
    underline = "=" * max(len(title), 2)
    return f"{title}\r\n{underline}\r\n\r\n".encode("utf-8")


def _posix(p: str) -> str:
    return p.replace("\\", "/")


def _doc_name(rel_path: str) -> str:
    """Sphinx docname for a store-relative .rst path (no extension, posix)."""
    name = rel_path[:-4] if rel_path.lower().endswith(".rst") else rel_path
    return _posix(name)


def _entry_docname(entry: str, toctree_dir: str) -> str | None:
    """Resolve a toctree entry line's target to an absolute docname
    (srcdir-rooted, no leading slash), or None for non-entry lines."""
    entry = entry.strip()
    if not entry or entry.startswith(":"):
        return None
    m = _ENTRY_TARGET.search(entry)
    target = m.group(1).strip() if m else entry
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(toctree_dir, target))


def _replace_entry_target(line: str, new_target: str) -> str:
    """Rewrite the docname part of an entry line, keeping title/indent."""
    m = _ENTRY_TARGET.search(line)
    if m:
        return line[: m.start(1)] + new_target + line[m.end(1) :]
    indent = line[: len(line) - len(line.lstrip())]
    return indent + new_target


def _toctree_nodes(nodes: Iterable[EdNode]) -> list[EdNode]:
    return [n for n in nodes if n.type == "directive" and n.attrs.get("name") == "toctree"]


def _reassemble(nodes: list[EdNode]) -> str:
    return "".join(n.raw_source for n in nodes)


def add_toctree_entry(index_bytes: bytes, index_rel: str, new_doc_rel: str) -> bytes:
    """Append `new_doc_rel` (store-relative .rst path) to the first toctree
    of `index_rel`'s content. Returns the full new file bytes."""
    doc = parse_rst(index_bytes, index_rel, check_health=False)
    toctrees = _toctree_nodes(doc.nodes)
    if not toctrees:
        raise PageError(f"{index_rel} contains no .. toctree:: directive")
    node = toctrees[0]

    toctree_dir = posixpath.dirname(_posix(index_rel))
    target_doc = _doc_name(_posix(new_doc_rel))
    entry = posixpath.relpath(target_doc, start=toctree_dir or ".").replace("\\", "/")

    eol = _EOL.get(doc.eol, "\r\n")
    lines = node.raw_source.splitlines(keepends=True)

    # find indent from an existing entry, else default to option indent or 3
    entry_indent = None
    last_content_idx = 0
    for i, line in enumerate(lines[1:], start=1):
        stripped = line.rstrip("\r\n")
        if not stripped.strip():
            continue
        last_content_idx = i
        if not _OPTION_LINE.match(stripped):
            entry_indent = stripped[: len(stripped) - len(stripped.lstrip())]
    if entry_indent is None:
        for line in lines[1:]:
            stripped = line.rstrip("\r\n")
            if _OPTION_LINE.match(stripped):
                entry_indent = stripped[: len(stripped) - len(stripped.lstrip())]
                break
    if entry_indent is None:
        entry_indent = "   "

    if any(
        _entry_docname(l.rstrip("\r\n"), toctree_dir) == target_doc for l in lines[1:]
    ):
        raise PageError(f"{new_doc_rel} is already listed in this toctree")

    new_line = f"{entry_indent}{entry}{eol}"
    insert_at = last_content_idx + 1
    # entries must be separated from options by a blank line; if the last
    # content line is an option, insert after the blank that follows it
    if last_content_idx >= 1 and _OPTION_LINE.match(lines[last_content_idx].rstrip("\r\n")):
        if insert_at < len(lines) and not lines[insert_at].rstrip("\r\n").strip():
            insert_at += 1
        else:
            new_line = eol + new_line
    lines.insert(insert_at, new_line)

    node.raw_source = "".join(lines)
    return _reassemble(doc.nodes).encode(doc.encoding)


def _entry_line_indices(lines: list[str], file_rel: str) -> list[int]:
    """Indices (into `lines`) of the toctree block's entry lines, in order —
    the positions the TOC UI's reorder/remove operations refer to."""
    toctree_dir = posixpath.dirname(_posix(file_rel))
    return [
        i
        for i, line in enumerate(lines[1:], start=1)
        if _entry_docname(line.rstrip("\r\n"), toctree_dir) is not None
    ]


def _rewrite_nth_toctree(
    index_bytes: bytes, index_rel: str, toctree_index: int, mutate
) -> bytes:
    """Parse, apply `mutate(lines, entry_indices)` to the nth toctree block's
    lines (keepends), reassemble everything else verbatim."""
    doc = parse_rst(index_bytes, index_rel, check_health=False)
    toctrees = _toctree_nodes(doc.nodes)
    if toctree_index < 0 or toctree_index >= len(toctrees):
        raise PageError(f"{index_rel} has no toctree #{toctree_index}")
    node = toctrees[toctree_index]
    lines = node.raw_source.splitlines(keepends=True)
    mutate(lines, _entry_line_indices(lines, index_rel))
    node.raw_source = "".join(lines)
    return _reassemble(doc.nodes).encode(doc.encoding)


def reorder_toctree_entry(
    index_bytes: bytes, index_rel: str, toctree_index: int, from_pos: int, to_pos: int
) -> bytes:
    def mutate(lines: list[str], entries: list[int]) -> None:
        if not (0 <= from_pos < len(entries)) or not (0 <= to_pos < len(entries)):
            raise PageError("entry position out of range")
        # permute only the entry lines; options, blanks, and any interleaved
        # text keep their exact bytes and positions
        entry_lines = [lines[i] for i in entries]
        moved = entry_lines.pop(from_pos)
        entry_lines.insert(to_pos, moved)
        for slot, text in zip(entries, entry_lines, strict=True):
            lines[slot] = text

    return _rewrite_nth_toctree(index_bytes, index_rel, toctree_index, mutate)


def remove_toctree_entry(
    index_bytes: bytes, index_rel: str, toctree_index: int, position: int
) -> bytes:
    def mutate(lines: list[str], entries: list[int]) -> None:
        if not (0 <= position < len(entries)):
            raise PageError("entry position out of range")
        del lines[entries[position]]

    return _rewrite_nth_toctree(index_bytes, index_rel, toctree_index, mutate)


def update_toctree_references(
    file_bytes: bytes, file_rel: str, old_doc_rel: str, new_doc_rel: str
) -> bytes | None:
    """Rewrite toctree entries in one file that point at `old_doc_rel`.
    Returns new bytes, or None if the file references nothing to change."""
    if b"toctree" not in file_bytes:
        return None
    doc = parse_rst(file_bytes, file_rel, check_health=False)
    toctrees = _toctree_nodes(doc.nodes)
    if not toctrees:
        return None

    toctree_dir = posixpath.dirname(_posix(file_rel))
    old_doc = _doc_name(_posix(old_doc_rel))
    new_doc = _doc_name(_posix(new_doc_rel))
    changed = False

    for node in toctrees:
        lines = node.raw_source.splitlines(keepends=True)
        for i, line in enumerate(lines[1:], start=1):
            stripped = line.rstrip("\r\n")
            if _entry_docname(stripped, toctree_dir) != old_doc:
                continue
            m = _ENTRY_TARGET.search(stripped)
            target = m.group(1).strip() if m else stripped.strip()
            if target.startswith("/"):
                new_target = "/" + new_doc
            else:
                new_target = posixpath.relpath(new_doc, start=toctree_dir or ".").replace("\\", "/")
            eol = line[len(stripped):]
            lines[i] = _replace_entry_target(stripped, new_target) + eol
            changed = True
        if changed:
            node.raw_source = "".join(lines)

    if not changed:
        return None
    return _reassemble(doc.nodes).encode(doc.encoding)
