"""view tree -> ProseMirror JSON, mirroring the frontend's convert.ts.

Used by tests and the CLI --strict metric to exercise the serializer over
the whole corpus without a browser: parse -> view -> (this bridge) -> PM ->
serialize -> verify. Blocks convert.ts would turn into opaque cards raise
UnsupportedView here and are skipped — they can never arrive as `node`
blocks from the real frontend either.

If convert.ts changes shape, change this file to match (drift is caught by
the strict metric suddenly failing, and at runtime every save is still
independently guarded by verify-reparse).
"""

from __future__ import annotations

from typing import Any

from .model import EdNode

PMNode = dict[str, Any]


class UnsupportedView(Exception):
    pass


_MARK_BY_VIEW = {
    "strong": "strong",
    "em": "em",
    "literal": "code",
    "superscript": "sup",
    "subscript": "sub",
    "title_ref": "title_ref",
}


def _inline(nodes: list[dict], marks: list[dict]) -> list[PMNode]:
    out: list[PMNode] = []
    for node in nodes or []:
        t = node.get("type")
        if t == "text":
            text = node.get("text", "")
            if text:
                item: PMNode = {"type": "text", "text": text}
                if marks:
                    item["marks"] = marks
                out.append(item)
        elif t == "math":
            out.append({"type": "inline_math", "attrs": {"tex": node.get("text", "")}})
        elif t == "subst_ref":
            out.append({"type": "subst_ref", "attrs": {"name": node.get("name", "")}})
        elif t == "link":
            m = marks + [{"type": "link", "attrs": {"href": node.get("href", "")}}]
            out.extend(_inline(node.get("children") or [], m))
        elif t in _MARK_BY_VIEW:
            m = marks + [{"type": _MARK_BY_VIEW[t]}]
            out.extend(_inline(node.get("children") or [], m))
        elif t == "opaque":
            text = node.get("text", "")
            if text:
                out.append({"type": "text", "text": text, "marks": marks + [{"type": "opaque"}]})
        else:
            raise UnsupportedView(f"inline {t!r}")
    return out


def pm_from_view(view: dict) -> PMNode:
    t = view.get("type")
    if t == "paragraph":
        return {"type": "paragraph", "content": _inline(view.get("children") or [], [])}
    if t == "literal_block":
        text = view.get("text", "")
        return {"type": "literal_block", "content": [{"type": "text", "text": text}] if text else []}
    if t == "block_quote":
        return {"type": "blockquote", "content": [pm_from_view(c) for c in view.get("children") or []]}
    if t in ("bullet_list", "enumerated_list"):
        pm_type = "bullet_list" if t == "bullet_list" else "ordered_list"
        items = []
        for item in view.get("children") or []:
            items.append(
                {"type": "list_item", "content": [pm_from_view(c) for c in item.get("children") or []]}
            )
        return {"type": pm_type, "content": items}
    if t == "block_group":
        return {"type": "block_group", "content": [pm_from_view(c) for c in view.get("children") or []]}
    if t == "csv_table":
        return _pm_from_csv_table(view)
    raise UnsupportedView(f"block {t!r}")


def _pm_from_csv_cell(cell: dict, cell_type: str) -> PMNode:
    content = _inline(cell.get("children") or [], [])
    attrs = {
        "csvRaw": cell.get("raw", ""),
        "csvPrefix": cell.get("prefix", ""),
        "csvQuoted": bool(cell.get("quoted", True)),
        "csvInitialContent": content,
    }
    return {
        "type": cell_type,
        "attrs": attrs,
        "content": [{"type": "paragraph", "content": content}],
    }


def _pm_from_csv_row(row: dict, cell_type: str) -> PMNode:
    return {
        "type": "table_row",
        "attrs": {"csvRaw": row.get("raw", ""), "csvCellCount": len(row.get("cells") or [])},
        "content": [_pm_from_csv_cell(cell, cell_type) for cell in row.get("cells") or []],
    }


def _pm_from_csv_table(view: dict) -> PMNode:
    rows = []
    header = view.get("header")
    if header:
        rows.append(_pm_from_csv_row(header, "table_header"))
    rows.extend(_pm_from_csv_row(row, "table_cell") for row in view.get("rows") or [])
    if not rows:
        raise UnsupportedView("empty csv_table")
    return {
        "type": "table",
        "attrs": {
            "csv": {
                "kind": "csv_table",
                "caption": view.get("caption", ""),
                "directive": view.get("directive", ""),
                "indent": view.get("indent", "   "),
                "delimiter": view.get("delimiter", ","),
                "quote": view.get("quote", '"'),
                "options": view.get("options") or [],
                "hasHeader": bool(header),
            }
        },
        "content": rows,
    }


def pm_from_heading(node: EdNode) -> PMNode:
    content: list[PMNode]
    if node.view and node.view.get("type") == "heading_title":
        try:
            content = _inline(node.view.get("children") or [], [])
        except UnsupportedView:
            content = [{"type": "text", "text": str(node.attrs.get("title", ""))}]
    else:
        title = str(node.attrs.get("title", ""))
        content = [{"type": "text", "text": title}] if title else []
    return {
        "type": "heading",
        "attrs": {
            "underline": node.attrs.get("underline", "="),
            "overline": bool(node.attrs.get("overline")),
        },
        "content": content,
    }
