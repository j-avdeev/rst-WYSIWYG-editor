"""Serialize a ProseMirror block (JSON, as sent by the frontend) to rst text.

Only *dirty* blocks ever pass through here — clean blocks re-emit their
original raw_source verbatim (see assemble.py). Every result is verified by
re-parsing before a save is allowed (rstkit.verify), so this serializer's
contract is "produce rst whose parse means what the editor showed", not
"reproduce original formatting". Consequences, by design:

- Edited paragraphs are emitted as a single line (original hard-wrapping is
  not reconstructed). The diff still touches only the edited block.
- Inline markup that rst cannot express (nested marks like bold+italic on
  one run) is reduced to the highest-priority mark before serializing; the
  same reduction is applied on the verify side, and the editor shows the
  truth after the post-save refetch.
"""

from __future__ import annotations

import re
from typing import Any

PMNode = dict[str, Any]


class SerializeError(Exception):
    """The PM structure cannot be expressed in rst by this serializer."""


# --------------------------------------------------------------------------
# marks

# rst has no nested inline markup: one winning mark per text run.
MARK_PRIORITY = ["link", "code", "strong", "em", "sup", "sub", "title_ref"]


def normalize_mark(marks: list[dict] | None) -> tuple[str, str] | None:
    """Reduce a PM mark list to the single serializable mark: ("strong", "")
    or ("link", href) or None. The 'opaque' mark is display-only and drops
    to plain text."""
    if not marks:
        return None
    present = {m["type"]: m for m in marks}
    for name in MARK_PRIORITY:
        if name in present:
            href = str(present[name].get("attrs", {}).get("href", "")) if name == "link" else ""
            return (name, href)
    return None  # only unserializable marks (e.g. 'opaque')


# --------------------------------------------------------------------------
# inline text escaping

_ESCAPE_CHARS = re.compile(r"([\\`*|])")
# an underscore that ends a word (what rst would read as a reference suffix)
_TRAILING_UNDERSCORE = re.compile(r"(?<=\w)_(?=[\s\W]|$)")
# docutils auto-links standalone emails ("a@b.c") and scheme URIs
# ("http://x", "mailto:x") in plain text; escaping the @ / the scheme colon
# breaks that recognition without changing the rendered text (fuzz-found:
# plain "0@*" re-parsed as a mailto reference)
_SCHEME_COLON = re.compile(r"(?<=[A-Za-z0-9])(:)(?=\S)")


_SOFT_WRAP = re.compile(r"[ \t]*\n[ \t]*")


def collapse_soft_wraps(text: str) -> str:
    """docutils astext() keeps source soft-wraps as newlines; an edited
    paragraph re-flows to a single line (design decision, see module doc).
    Tabs become spaces (the rst parser expands them anyway, so they can't
    round-trip), and stray docutils NUL escape markers are dropped."""
    return _SOFT_WRAP.sub(" ", text).replace("\t", " ").replace("\x00", "")


def escape_text(text: str) -> str:
    text = _ESCAPE_CHARS.sub(r"\\\1", text)
    text = _TRAILING_UNDERSCORE.sub(r"\\_", text)
    text = text.replace("@", "\\@")
    text = _SCHEME_COLON.sub(r"\\:", text)
    return text


# a serialized paragraph line must not be mistaken for block-level markup;
# list/comment markers count both mid-line ("- x") and bare at end-of-line
# ("-" alone is an empty bullet item — fuzz-found). rst enumerators are not
# just arabic: alphabetic ("A."), roman ("X)" — fuzz-found), "#", and the
# parenthesized form "(x)" all count; over-guarding is harmless since the
# backslash escape vanishes at parse.
_ENUM = r"(\d+|[A-Za-z]|[ivxlcdm]+|[IVXLCDM]+|#)"
_BLOCK_START = re.compile(
    r"^(\.\.(\s|$)|::|\s|[-*+](\s|$)"
    rf"|{_ENUM}[.)](\s|$)"
    rf"|\({_ENUM}\)(\s|$)"
    r"|>>>\s|\|(\s|$)|:[\w.-]+:(\s|$))"
)


def guard_line_start(line: str) -> str:
    if not line:
        return line
    first = line[0]
    if _BLOCK_START.match(line) and first != "\\":
        return "\\" + line
    # a line made entirely of one punctuation char would parse as a
    # transition / stray adornment
    stripped = line.strip()
    if len(stripped) >= 2 and not stripped[0].isalnum() and stripped == stripped[0] * len(stripped):
        return "\\" + line
    return line


# --------------------------------------------------------------------------
# inline serialization

def _wrap(mark: tuple[str, str] | None, text: str) -> str:
    if mark is None:
        return escape_text(text)
    kind, href = mark
    if kind == "strong":
        return f"**{escape_text(text)}**"
    if kind == "em":
        return f"*{escape_text(text)}*"
    if kind == "code":
        if "``" in text:
            raise SerializeError("literal text cannot contain ``")
        if text.startswith("`") or text.endswith("`"):
            # would merge with the ``...`` delimiters
            raise SerializeError("literal text cannot start or end with a backtick")
        return f"``{text}``"
    if kind == "link":
        body = text.replace("`", "\\`")
        return f"`{body} <{href}>`__"
    if kind == "sup":
        return f":sup:`{_role_body(text)}`"
    if kind == "sub":
        return f":sub:`{_role_body(text)}`"
    if kind == "title_ref":
        return f"`{_role_body(text)}`"
    raise SerializeError(f"unknown mark {kind}")


def _role_body(text: str) -> str:
    if "`" in text:
        raise SerializeError("role content cannot contain a backtick")
    return text


def _is_markup_wrapped(mark: tuple[str, str] | None) -> bool:
    return mark is not None


def serialize_inline(content: list[PMNode]) -> str:
    """PM inline content -> one line of rst."""
    # 1. fold to a list of (kind, payload) segments, merging adjacent text
    #    runs whose normalized mark is identical (adjacent **a****b** would
    #    not re-parse).
    segments: list[tuple[str, Any]] = []
    for item in content or []:
        t = item.get("type")
        if t == "text":
            mark = normalize_mark(item.get("marks"))
            text = collapse_soft_wraps(item.get("text", ""))
            if not text:
                continue
            if segments and segments[-1][0] == "text" and segments[-1][1][0] == mark:
                segments[-1] = ("text", (mark, segments[-1][1][1] + text))
            else:
                segments.append(("text", (mark, text)))
        elif t == "inline_math":
            tex = str(item.get("attrs", {}).get("tex", ""))
            segments.append(("math", tex))
        elif t == "subst_ref":
            name = str(item.get("attrs", {}).get("name", ""))
            segments.append(("subst", name))
        elif t == "hard_break":
            raise SerializeError("hard line breaks are not supported")
        else:
            raise SerializeError(f"unknown inline node {t!r}")

    # 2. emit, inserting escaped-space separators where markup would touch
    #    word characters (rst inline recognition rules). Whitespace at the
    #    edges of a marked run moves OUTSIDE the markup ("** a**" is invalid
    #    rst); marks on pure whitespace are invisible and drop to plain text.
    #    The canonical form (verify._merge_leaves) applies the same
    #    normalization, so both sides stay comparable.
    out: list[str] = []
    prev_needs_gap_after = False  # previous piece ended with a markup end-string
    prev_char = ""
    for kind, payload in segments:
        if kind == "text":
            mark, text = payload
            core = text.strip()
            if mark is None or not core:
                wrapped = False
                piece = escape_text(text)
            else:
                lead = text[: len(text) - len(text.lstrip())]
                trail = text[len(text.rstrip()) :]
                wrapped = True
                piece = lead + _wrap(mark, core) + trail
        elif kind == "math":
            if "`" in payload:
                raise SerializeError("math content cannot contain a backtick")
            wrapped = True
            piece = f":math:`{payload}`"
        else:  # subst
            if "|" in payload:
                raise SerializeError("substitution name cannot contain |")
            wrapped = True
            piece = f"|{payload}|"

        if not piece:
            continue
        starts_with_markup = wrapped and not piece[0].isspace()
        if starts_with_markup and prev_char and not _boundary_ok(prev_char):
            out.append("\\ ")
        if prev_needs_gap_after and piece and not _boundary_ok(piece[0]):
            out.append("\\ ")
        out.append(piece)
        prev_needs_gap_after = wrapped and not piece[-1].isspace()
        prev_char = piece[-1]
    # leading/trailing whitespace on the assembled line cannot survive an rst
    # round-trip (it would change block structure); canon trims it identically
    return "".join(out).strip()


def _boundary_ok(ch: str) -> bool:
    """Chars next to which inline markup start/end strings are recognized
    (docutils uses Unicode punctuation categories, so «»—etc. qualify)."""
    return not ch.isalnum()


# --------------------------------------------------------------------------
# block serialization -> list of lines (no EOLs)

def serialize_block(node: PMNode) -> list[str]:
    t = node.get("type")
    if t == "paragraph":
        line = serialize_inline(node.get("content") or [])
        if not line.strip():
            raise SerializeError("empty paragraph")
        return [guard_line_start(line)]

    if t == "heading":
        return _serialize_heading(node)

    if t == "literal_block":
        text = "".join(c.get("text", "") for c in node.get("content") or [])
        if not text.strip():
            raise SerializeError("empty literal block")
        return ["::", ""] + _indent_lines(text.split("\n"), 3)

    if t in ("bullet_list", "ordered_list"):
        return _serialize_list(node)

    if t == "blockquote":
        inner = _serialize_children(node.get("content") or [])
        return _indent_lines(inner, 4)

    if t == "block_group":
        return _serialize_group(node.get("content") or [])

    if t == "table" and (node.get("attrs") or {}).get("csv", {}).get("kind") == "csv_table":
        from .tables import serialize_csv_table_pm

        return serialize_csv_table_pm(node)

    if t == "opaque_block":
        raw = str(node.get("attrs", {}).get("raw", ""))
        return raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    raise SerializeError(f"unsupported block type {t!r}")


def _serialize_heading(node: PMNode) -> list[str]:
    attrs = node.get("attrs", {})
    title = serialize_inline(node.get("content") or []).strip()
    if not title:
        raise SerializeError("empty heading")
    # a title like "1. Overview" must not re-read as a list/directive when
    # the title line is considered on its own
    title = guard_line_start(title)
    char = str(attrs.get("underline", "=")) or "="
    line = char[0] * max(len(title), 2)
    if attrs.get("overline"):
        return [line, title, line]
    return [title, line]


def _serialize_list(node: PMNode) -> list[str]:
    ordered = node.get("type") == "ordered_list"
    items = node.get("content") or []
    if not items:
        raise SerializeError("empty list")
    lines: list[str] = []
    multi_block = any(len(item.get("content") or []) > 1 for item in items)
    for idx, item in enumerate(items):
        if item.get("type") != "list_item":
            raise SerializeError(f"unexpected list child {item.get('type')!r}")
        marker = f"{idx + 1}. " if ordered else "- "
        pad = " " * len(marker)
        inner = _serialize_children(item.get("content") or [])
        if not inner:
            raise SerializeError("empty list item")
        first = True
        for ln in inner:
            if first and ln:
                lines.append(marker + ln)
                first = False
            elif first:
                lines.append(marker.rstrip())
                first = False
            else:
                lines.append(pad + ln if ln else "")
        if multi_block and idx < len(items) - 1:
            lines.append("")
    return lines


def _serialize_children(children: list[PMNode]) -> list[str]:
    """Serialize a sequence of sibling blocks (list-item body, blockquote
    body, block_group). A paragraph directly followed by a literal block is
    re-linked with the ``::`` marker so the pair re-parses as it displayed."""
    lines: list[str] = []
    i = 0
    while i < len(children):
        child = children[i]
        nxt = children[i + 1] if i + 1 < len(children) else None
        if (
            child.get("type") == "paragraph"
            and nxt is not None
            and nxt.get("type") == "literal_block"
        ):
            para = serialize_inline(child.get("content") or []).rstrip()
            if not para:
                raise SerializeError("empty paragraph")
            intro = para[:-1] + "::" if para.endswith(":") else para + " ::"
            text = "".join(c.get("text", "") for c in nxt.get("content") or [])
            if not text.strip():
                raise SerializeError("empty literal block")
            if lines:
                lines.append("")
            lines.append(guard_line_start(intro))
            lines.append("")
            lines.extend(_indent_lines(text.split("\n"), 3))
            i += 2
            continue
        if lines:
            lines.append("")
        lines.extend(serialize_block(child))
        i += 1
    return lines


def _serialize_group(children: list[PMNode]) -> list[str]:
    return _serialize_children(children)


def _indent_lines(lines: list[str], width: int) -> list[str]:
    pad = " " * width
    return [pad + ln if ln.strip() else "" for ln in lines]
