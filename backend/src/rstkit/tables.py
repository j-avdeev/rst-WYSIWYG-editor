"""csv-table parsing and serialization helpers.

The table view is deliberately conservative: unsupported dialects, ragged
rows, multiline CSV records, or cells that cannot be represented as inline
content return ``None`` so the owning directive stays an opaque raw-source
card. Clean-cell raw tokens are carried through the PM attrs so editing one
cell can rewrite only that CSV line while neighboring cells keep their exact
quoting and spacing.
"""

from __future__ import annotations

import csv
import re
from typing import Any

PMNode = dict[str, Any]

_DIRECTIVE_RE = re.compile(r"^(\s*)\.\.[ \t]+csv-table::[ \t]*(.*)$")
_OPTION_RE = re.compile(r"^:([\w-]+):(?:[ \t]*(.*))?$")


def _strip_eol(line: str) -> str:
    return line.rstrip("\r\n")


def _is_blank(line: str) -> bool:
    return not _strip_eol(line).strip()


def _indent_width(line: str) -> int:
    s = _strip_eol(line).expandtabs(8)
    return len(s) - len(s.lstrip(" "))


def _dedent_line(line: str, width: int) -> str | None:
    stripped = _strip_eol(line)
    if not stripped.strip():
        return ""
    if _indent_width(stripped) < width:
        return None
    return stripped[width:]


def _directive_indent(lines: list[str], base_indent: int) -> int:
    indents = [
        _indent_width(line)
        for line in lines[1:]
        if _strip_eol(line).strip() and _indent_width(line) > base_indent
    ]
    return min(indents) if indents else base_indent + 3


def _dialect_value(value: str) -> str:
    value = value.strip()
    if value.lower() == "tab":
        return "\t"
    if value.lower() == "space":
        return " "
    if len(value) == 1:
        return value
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        inner = value[1:-1]
        if len(inner) == 1:
            return inner
    raise ValueError(f"unsupported csv dialect value {value!r}")


def _parse_csv_tokens(line: str, delimiter: str, quotechar: str) -> list[dict[str, Any]] | None:
    if len(delimiter) != 1 or len(quotechar) != 1:
        return None
    try:
        parsed = next(
            csv.reader([line], delimiter=delimiter, quotechar=quotechar, skipinitialspace=True)
        )
    except csv.Error:
        return None

    tokens: list[dict[str, Any]] = []
    start = 0
    in_quote = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == quotechar:
            if in_quote and i + 1 < len(line) and line[i + 1] == quotechar:
                i += 2
                continue
            in_quote = not in_quote
        elif ch == delimiter and not in_quote:
            tokens.append({"raw": line[start:i]})
            start = i + 1
        i += 1
    if in_quote:
        return None
    tokens.append({"raw": line[start:]})
    if len(tokens) != len(parsed):
        return None
    for token, value in zip(tokens, parsed, strict=True):
        raw = str(token["raw"])
        lstripped = raw.lstrip(" \t")
        token["text"] = value
        token["prefix"] = raw[: len(raw) - len(lstripped)]
        token["quoted"] = lstripped.startswith(quotechar)
    return tokens


def _inline_children(text: str) -> list[dict] | None:
    if not text:
        return []
    # Local import avoids a cycle: inline.py imports this module for directive
    # enrichment, and the table parser reuses inline.py's safe fragment parser.
    from .inline import text_to_view

    view = text_to_view(text + "\n")
    if view is None or view.get("type") != "paragraph":
        return None
    return view.get("children") or []


def _cell_from_token(token: dict[str, Any]) -> dict[str, Any] | None:
    children = _inline_children(str(token.get("text", "")))
    if children is None:
        return None
    return {
        "type": "csv_cell",
        "text": token["text"],
        "raw": token["raw"],
        "prefix": token["prefix"],
        "quoted": token["quoted"],
        "children": children,
    }


def _parse_row(line: str, delimiter: str, quotechar: str) -> dict[str, Any] | None:
    tokens = _parse_csv_tokens(line, delimiter, quotechar)
    if tokens is None:
        return None
    cells = []
    for token in tokens:
        cell = _cell_from_token(token)
        if cell is None:
            return None
        cells.append(cell)
    return {"raw": line, "cells": cells}


def csv_table_to_view(raw_source: str) -> dict[str, Any] | None:
    """Return a structured csv-table view, or ``None`` to keep it opaque."""
    lines = raw_source.splitlines(keepends=True)
    while lines and _is_blank(lines[-1]):
        lines.pop()
    if not lines:
        return None

    first = _strip_eol(lines[0])
    m = _DIRECTIVE_RE.match(first)
    if not m:
        return None
    base_indent = len(m.group(1).expandtabs(8))
    caption = m.group(2).strip()
    content_indent = _directive_indent(lines, base_indent)
    indent = " " * content_indent

    options: list[dict[str, str]] = []
    i = 1
    while i < len(lines):
        if _is_blank(lines[i]):
            i += 1
            break
        dedented = _dedent_line(lines[i], content_indent)
        if dedented is None:
            return None
        opt = _OPTION_RE.match(dedented)
        if opt is None:
            break
        name = opt.group(1).lower()
        value = (opt.group(2) or "").rstrip()
        options.append({"name": name, "value": value, "raw": _strip_eol(lines[i])})
        i += 1

    while i < len(lines) and _is_blank(lines[i]):
        i += 1

    if any(opt["name"] == "file" for opt in options):
        return None

    delimiter = ","
    quotechar = '"'
    try:
        for opt in options:
            if opt["name"] in {"delim", "delimiter"}:
                delimiter = _dialect_value(opt["value"])
            elif opt["name"] == "quote":
                quotechar = _dialect_value(opt["value"])
    except ValueError:
        return None

    header_row: dict[str, Any] | None = None
    for opt in options:
        if opt["name"] == "header":
            header_row = _parse_row(opt["value"], delimiter, quotechar)
            if header_row is None:
                return None

    rows: list[dict[str, Any]] = []
    for line in lines[i:]:
        if _is_blank(line):
            continue
        dedented = _dedent_line(line, content_indent)
        if dedented is None:
            return None
        row = _parse_row(dedented, delimiter, quotechar)
        if row is None:
            return None
        rows.append(row)

    if header_row is None and not rows:
        return None

    width = len(header_row["cells"]) if header_row is not None else len(rows[0]["cells"])
    all_rows = ([header_row] if header_row is not None else []) + rows
    if width == 0 or any(len(row["cells"]) != width for row in all_rows if row is not None):
        return None

    return {
        "type": "csv_table",
        "caption": caption,
        "directive": first,
        "indent": indent,
        "delimiter": delimiter,
        "quote": quotechar,
        "options": options,
        "header": header_row,
        "rows": rows,
    }


def _cell_initial_content(cell: dict[str, Any]) -> list[PMNode]:
    content = cell.get("content") or []
    if len(content) != 1 or content[0].get("type") != "paragraph":
        return []
    return content[0].get("content") or []


def _cell_current_content(cell: dict[str, Any]) -> list[PMNode]:
    content = cell.get("content") or []
    if len(content) != 1 or content[0].get("type") != "paragraph":
        from .pmserialize import SerializeError

        raise SerializeError("csv-table cells support one paragraph only")
    return content[0].get("content") or []


def _csv_quote(value: str, *, raw: str, prefix: str, quoted: bool, delimiter: str, quotechar: str) -> str:
    must_quote = quoted or value == "" or value != value.strip() or any(
        ch in value for ch in (delimiter, quotechar, "\n", "\r")
    )
    if not must_quote:
        return prefix + value
    escaped = value.replace(quotechar, quotechar * 2)
    return f"{prefix}{quotechar}{escaped}{quotechar}"


def _serialize_cell(cell: dict[str, Any], delimiter: str, quotechar: str) -> str:
    from .pmserialize import serialize_inline

    attrs = cell.get("attrs") or {}
    current = _cell_current_content(cell)
    initial = attrs.get("csvInitialContent")
    raw = str(attrs.get("csvRaw", ""))
    if initial == current and raw:
        return raw
    value = serialize_inline(current)
    return _csv_quote(
        value,
        raw=raw,
        prefix=str(attrs.get("csvPrefix", "")),
        quoted=bool(attrs.get("csvQuoted", True)),
        delimiter=delimiter,
        quotechar=quotechar,
    )


def _serialize_pm_row(row: dict[str, Any], delimiter: str, quotechar: str) -> str:
    from .pmserialize import SerializeError

    if row.get("type") != "table_row":
        raise SerializeError("csv-table expected table_row")
    cells = row.get("content") or []
    if not cells:
        raise SerializeError("csv-table row is empty")
    return delimiter.join(_serialize_cell(cell, delimiter, quotechar) for cell in cells)


def _row_is_clean(row: dict[str, Any]) -> bool:
    attrs = row.get("attrs") or {}
    cells = row.get("content") or []
    if not attrs.get("csvRaw"):
        return False
    original_count = attrs.get("csvCellCount")
    if not isinstance(original_count, int) or original_count != len(cells):
        return False
    for cell in cells:
        attrs = cell.get("attrs") or {}
        if attrs.get("csvInitialContent") != _cell_initial_content(cell):
            return False
    return True


def serialize_csv_table_pm(pm: PMNode) -> list[str]:
    from .pmserialize import SerializeError

    attrs = pm.get("attrs") or {}
    meta = attrs.get("csv") or {}
    if meta.get("kind") != "csv_table":
        raise SerializeError("unsupported table node")

    delimiter = str(meta.get("delimiter", ","))
    quotechar = str(meta.get("quote", '"'))
    indent = str(meta.get("indent", "   "))
    if len(delimiter) != 1 or len(quotechar) != 1:
        raise SerializeError("csv-table uses unsupported dialect")

    rows = pm.get("content") or []
    if not rows:
        raise SerializeError("csv-table has no rows")

    header_enabled = bool(meta.get("hasHeader"))
    body_rows = rows[1:] if header_enabled else rows
    lines = [str(meta.get("directive") or f".. csv-table:: {meta.get('caption', '')}".rstrip())]

    options = meta.get("options") or []
    header_written = False
    for opt in options:
        name = str(opt.get("name", "")).lower()
        if name == "header":
            if not header_enabled:
                continue
            header = rows[0]
            if _row_is_clean(header) and opt.get("raw"):
                lines.append(str(opt["raw"]))
            else:
                lines.append(f"{indent}:header: {_serialize_pm_row(header, delimiter, quotechar)}")
            header_written = True
        else:
            raw = opt.get("raw")
            if raw:
                lines.append(str(raw))
            else:
                lines.append(f"{indent}:{name}: {opt.get('value', '')}".rstrip())

    if header_enabled and not header_written:
        lines.append(f"{indent}:header: {_serialize_pm_row(rows[0], delimiter, quotechar)}")

    if body_rows:
        lines.append("")
        for row in body_rows:
            row_attrs = row.get("attrs") or {}
            if _row_is_clean(row) and row_attrs.get("csvRaw"):
                lines.append(indent + str(row_attrs["csvRaw"]))
            else:
                lines.append(indent + _serialize_pm_row(row, delimiter, quotechar))
    return lines
