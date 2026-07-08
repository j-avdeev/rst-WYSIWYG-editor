"""Verify-reparse: prove that serialized rst means what the editor showed.

Both sides — the PM block the frontend sent, and the re-parsed view tree of
the rst we produced for it — are reduced to the same *canonical form*:

- inline content flattens to leaves: ("text", str, mark) / ("math", tex) /
  ("subst", name), with adjacent same-mark text leaves merged and marks
  reduced exactly the way the serializer reduces them (rst can't nest
  inline markup, so only the highest-priority mark survives);
- blocks become nested tuples by type.

If the canonical forms differ, the save is rejected (VerifyError) — a
serializer bug or an inexpressible construct can never corrupt a file.
"""

from __future__ import annotations

from typing import Any

from .inline import text_to_view, title_to_view
from .parse import scan_blocks
from .pmserialize import PMNode, collapse_soft_wraps, normalize_mark, serialize_block

Canon = tuple  # nested tuples, fully hashable/comparable


class VerifyError(Exception):
    def __init__(self, message: str, expected: Any = None, actual: Any = None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


# --------------------------------------------------------------------------
# canonical form: inline

def _merge_leaves(leaves: list[tuple]) -> tuple:
    merged: list[tuple] = []
    for leaf in leaves:
        if leaf[0] == "text":
            # paragraphs re-flow on edit, so soft-wrap position is not part
            # of the meaning being verified
            leaf = ("text", collapse_soft_wraps(leaf[1]), leaf[2])
        if not (leaf[0] == "text" and leaf[1] == ""):
            if merged and leaf[0] == "text" and merged[-1][0] == "text" and merged[-1][2] == leaf[2]:
                merged[-1] = ("text", merged[-1][1] + leaf[1], leaf[2])
            else:
                merged.append(leaf)
    return tuple(merged)


_VIEW_MARK = {
    "strong": "strong",
    "em": "em",
    "literal": "code",
    "superscript": "sup",
    "subscript": "sub",
    "title_ref": "title_ref",
}


def _view_inline_leaves(nodes: list[dict], inherited: list[tuple[str, str]]) -> list[tuple]:
    leaves: list[tuple] = []
    for node in nodes or []:
        t = node.get("type")
        if t == "text":
            mark = _reduce_marks(inherited)
            leaves.append(("text", node.get("text", ""), mark))
        elif t == "math":
            leaves.append(("math", node.get("text", "")))
        elif t == "subst_ref":
            leaves.append(("subst", node.get("name", "")))
        elif t == "link":
            marks = inherited + [("link", node.get("href", ""))]
            leaves.extend(_view_inline_leaves(node.get("children") or [], marks))
        elif t in _VIEW_MARK:
            marks = inherited + [(_VIEW_MARK[t], "")]
            leaves.extend(_view_inline_leaves(node.get("children") or [], marks))
        elif t == "opaque":
            mark = _reduce_marks(inherited)
            leaves.append(("text", node.get("text", ""), mark))
        else:
            raise VerifyError(f"unknown view inline type {t!r}")
    return leaves


def _reduce_marks(marks: list[tuple[str, str]]) -> tuple[str, str] | None:
    if not marks:
        return None
    pm_style = [{"type": k, "attrs": {"href": v}} for k, v in marks]
    return normalize_mark(pm_style)


def _pm_inline_leaves(content: list[PMNode]) -> list[tuple]:
    leaves: list[tuple] = []
    for item in content or []:
        t = item.get("type")
        if t == "text":
            leaves.append(("text", item.get("text", ""), normalize_mark(item.get("marks"))))
        elif t == "inline_math":
            leaves.append(("math", str(item.get("attrs", {}).get("tex", ""))))
        elif t == "subst_ref":
            leaves.append(("subst", str(item.get("attrs", {}).get("name", ""))))
        else:
            raise VerifyError(f"unknown pm inline type {t!r}")
    return leaves


# --------------------------------------------------------------------------
# canonical form: blocks

def canon_from_view(view: dict) -> Canon:
    t = view.get("type")
    if t == "paragraph":
        return ("paragraph", _merge_leaves(_view_inline_leaves(view.get("children") or [], [])))
    if t == "literal_block":
        return ("literal", view.get("text", ""))
    if t == "block_quote":
        return ("quote", tuple(canon_from_view(c) for c in view.get("children") or []))
    if t in ("bullet_list", "enumerated_list"):
        kind = "bullet" if t == "bullet_list" else "enum"
        items = tuple(
            tuple(canon_from_view(c) for c in item.get("children") or [])
            for item in view.get("children") or []
        )
        return (kind, items)
    if t == "block_group":
        return ("group", tuple(canon_from_view(c) for c in view.get("children") or []))
    raise VerifyError(f"unsupported view block {t!r}")


def canon_from_pm(node: PMNode) -> Canon:
    t = node.get("type")
    if t == "paragraph":
        return ("paragraph", _merge_leaves(_pm_inline_leaves(node.get("content") or [])))
    if t == "literal_block":
        text = "".join(c.get("text", "") for c in node.get("content") or [])
        return ("literal", text)
    if t == "blockquote":
        return ("quote", tuple(canon_from_pm(c) for c in node.get("content") or []))
    if t in ("bullet_list", "ordered_list"):
        kind = "bullet" if t == "bullet_list" else "enum"
        items = tuple(
            tuple(canon_from_pm(c) for c in item.get("content") or [])
            for item in node.get("content") or []
        )
        return (kind, items)
    if t == "block_group":
        return ("group", tuple(canon_from_pm(c) for c in node.get("content") or []))
    raise VerifyError(f"unsupported pm block {t!r}")


def _csv_cell_canon_from_pm(cell: PMNode) -> Canon:
    if cell.get("type") not in {"table_cell", "table_header"}:
        raise VerifyError(f"unexpected csv-table cell {cell.get('type')!r}")
    content = cell.get("content") or []
    if len(content) != 1 or content[0].get("type") != "paragraph":
        raise VerifyError("csv-table cells support one paragraph only")
    return _merge_leaves(_pm_inline_leaves(content[0].get("content") or []))


def _csv_canon_from_pm(table: PMNode) -> Canon:
    rows = []
    for row in table.get("content") or []:
        if row.get("type") != "table_row":
            raise VerifyError("csv-table expected table_row")
        rows.append(tuple(_csv_cell_canon_from_pm(cell) for cell in row.get("content") or []))
    return ("csv_table", tuple(rows))


def _csv_canon_from_view(view: dict) -> Canon:
    if view.get("type") != "csv_table":
        raise VerifyError(f"unsupported csv-table view {view.get('type')!r}")
    rows = []
    header = view.get("header")
    if header:
        rows.append(
            tuple(
                _merge_leaves(_view_inline_leaves(cell.get("children") or [], []))
                for cell in header.get("cells") or []
            )
        )
    for row in view.get("rows") or []:
        rows.append(
            tuple(
                _merge_leaves(_view_inline_leaves(cell.get("children") or [], []))
                for cell in row.get("cells") or []
            )
        )
    return ("csv_table", tuple(rows))


def _flatten_singleton_group(canon: Canon) -> Canon:
    # a one-child group is indistinguishable from its child after reparse
    while canon[0] == "group" and len(canon[1]) == 1:
        canon = canon[1][0]
    return canon


# --------------------------------------------------------------------------
# the verify loop

def serialize_and_verify_block(pm: PMNode) -> str:
    """Serialize a dirty PM block and prove the result re-parses to the same
    canonical form. Returns the rst text (LF-joined lines, no trailing EOL).
    Raises SerializeError/VerifyError on failure."""
    if pm.get("type") == "heading":
        return _serialize_and_verify_heading(pm)
    if pm.get("type") == "table" and (pm.get("attrs") or {}).get("csv", {}).get("kind") == "csv_table":
        return _serialize_and_verify_csv_table(pm)

    lines = serialize_block(pm)
    text = "\n".join(lines)
    if pm.get("type") == "opaque_block":
        return text  # raw passthrough: whole-file health gate covers it

    reparsed = text_to_view(text + "\n")
    if reparsed is None:
        raise VerifyError("serialized block did not re-parse", actual=text)
    expected = _flatten_singleton_group(canon_from_pm(pm))
    actual = _flatten_singleton_group(canon_from_view(reparsed))
    if expected != actual:
        raise VerifyError(
            "serialized block re-parses differently", expected=expected, actual=actual
        )
    return text


def _serialize_and_verify_csv_table(pm: PMNode) -> str:
    from .tables import csv_table_to_view

    lines = serialize_block(pm)
    text = "\n".join(lines)
    reparsed = csv_table_to_view(text + "\n")
    if reparsed is None:
        raise VerifyError("serialized csv-table did not re-parse", actual=text)
    expected = _csv_canon_from_pm(pm)
    actual = _csv_canon_from_view(reparsed)
    if expected != actual:
        raise VerifyError(
            "serialized csv-table re-parses differently", expected=expected, actual=actual
        )
    return text


def _serialize_and_verify_heading(pm: PMNode) -> str:
    lines = serialize_block(pm)
    text = "\n".join(lines)
    scanned = scan_blocks([ln + "\n" for ln in lines])
    if len(scanned) != 1 or scanned[0].type != "heading":
        raise VerifyError("serialized heading did not scan as a heading", actual=text)
    attrs = pm.get("attrs", {})
    node = scanned[0]
    if node.attrs.get("underline") != str(attrs.get("underline", "="))[0]:
        raise VerifyError("heading underline mismatch", actual=text)
    if bool(node.attrs.get("overline")) != bool(attrs.get("overline")):
        raise VerifyError("heading overline mismatch", actual=text)

    title_view = title_to_view(node.attrs.get("title", ""))
    if title_view is None:
        raise VerifyError("heading title did not re-parse", actual=text)
    expected = _merge_leaves(_pm_inline_leaves(pm.get("content") or []))
    actual = _merge_leaves(_view_inline_leaves(title_view.get("children") or [], []))
    if expected != actual:
        raise VerifyError("heading title re-parses differently", expected=expected, actual=actual)
    return text
