"""Best-effort rendering enrichment: turns "text" blocks into a paragraph /
list / literal-block / inline-mark tree for the frontend to render richly.

Design: each top-level "text" EdNode's raw_source is already an isolated,
self-contained span (the scanner guarantees that). We parse *that fragment
alone* through docutils and walk the resulting mini-doctree into a small,
frontend-friendly `view` dict. This sidesteps the "docutils line numbers are
unreliable" problem entirely — there is no matching against the outer file,
just a parse of a string we already know the boundaries of.

This module never touches `type`, `span`, `raw_source`, or `attrs` — the
fields the serializer depends on. A `view` of None (parse failed, or the
fragment doesn't map to a type this module understands) simply means the
frontend falls back to a plain preformatted block. Round-trip fidelity is
never at risk here.
"""

from __future__ import annotations

import re

from docutils import nodes as du
from docutils import frontend, utils
from docutils.parsers import rst

from .model import EdNode
from .parse import _register_stub_directives, _register_stub_roles


def _fragment_settings():
    settings = frontend.get_default_settings(rst.Parser)
    settings.report_level = 5
    settings.halt_level = 5
    settings.file_insertion_enabled = False
    settings.raw_enabled = False
    return settings


def _parse_fragment(text: str) -> du.document | None:
    try:
        _register_stub_directives(text)
        _register_stub_roles(text)
        document = utils.new_document("<fragment>", _fragment_settings())
        rst.Parser().parse(text, document)
        return document
    except Exception:
        return None


_INLINE_MARK = {
    du.strong: "strong",
    du.emphasis: "em",
    du.literal: "literal",
    du.title_reference: "title_ref",
    du.superscript: "superscript",
    du.subscript: "subscript",
}


_ESCAPED_WS = re.compile(r"\x00\s")


def _clean(text: str) -> str:
    """docutils marks backslash-escapes with NUL bytes in Text nodes and
    strips them in a writer transform we never run — apply the same
    semantics here: escaped whitespace vanishes entirely ("word\\ **b**"
    renders as "wordb"), other escaped chars keep the char."""
    return _ESCAPED_WS.sub("", text).replace("\x00", "")


def _convert_inline(node: du.Node) -> dict:
    if isinstance(node, du.Text):
        return {"type": "text", "text": _clean(str(node))}

    if isinstance(node, du.math):
        return {"type": "math", "text": _clean(node.astext())}

    if isinstance(node, du.substitution_reference):
        return {"type": "subst_ref", "name": _clean(node.get("refname", node.astext()))}

    if isinstance(node, du.reference):
        href = node.get("refuri") or node.get("refname") or ""
        return {
            "type": "link",
            "href": _clean(href),
            "children": [_convert_inline(c) for c in node.children] or [
                {"type": "text", "text": _clean(node.astext())}
            ],
        }

    for cls, mark in _INLINE_MARK.items():
        if isinstance(node, cls):
            return {
                "type": mark,
                "children": [_convert_inline(c) for c in node.children] or [
                    {"type": "text", "text": _clean(node.astext())}
                ],
            }

    # Unknown inline construct (footnote_reference, problematic role output,
    # etc.) — degrade to opaque text rather than dropping it.
    return {"type": "opaque", "text": _clean(node.astext())}


def _convert_inline_children(node: du.Node) -> list[dict]:
    return [_convert_inline(c) for c in node.children]


def _convert_block(node: du.Node) -> dict | None:
    """Convert one docutils block node to a view dict, or None if it (or ANY
    of its descendants) cannot be represented. Poisoning the whole block on
    an unconvertible child is a safety property: a view that silently drops
    a nested directive/comment would let an edit erase that content from the
    file. Unrepresentable => opaque card => raw source preserved."""
    if isinstance(node, du.paragraph):
        return {"type": "paragraph", "children": _convert_inline_children(node)}

    if isinstance(node, du.literal_block):
        return {"type": "literal_block", "text": node.astext()}

    if isinstance(node, du.block_quote):
        children = _convert_all_or_none(node.children)
        return {"type": "block_quote", "children": children} if children else None

    if isinstance(node, (du.bullet_list, du.enumerated_list)):
        kind = "bullet_list" if isinstance(node, du.bullet_list) else "enumerated_list"
        items = []
        for item in node.children:
            if not isinstance(item, du.list_item):
                return None
            item_children = _convert_all_or_none(item.children)
            if item_children is None:
                return None
            items.append({"type": "list_item", "children": item_children})
        return {"type": kind, "children": items} if items else None

    if isinstance(node, du.definition_list):
        items = []
        for item in node.children:
            if not isinstance(item, du.definition_list_item):
                return None
            term = item.first_child_matching_class(du.term)
            definition = item.first_child_matching_class(du.definition)
            if term is None or definition is None:
                return None
            def_children = _convert_all_or_none(item[definition].children)
            if def_children is None:
                return None
            items.append(
                {
                    "type": "definition_item",
                    "term": _convert_inline_children(item[term]),
                    "children": def_children,
                }
            )
        return {"type": "definition_list", "children": items} if items else None

    if isinstance(node, du.line_block):
        lines = []
        for c in node.children:
            if not isinstance(c, du.line):
                return None
            lines.append({"type": "line", "children": _convert_inline_children(c)})
        return {"type": "line_block", "children": lines} if lines else None

    return None


def _convert_all_or_none(children: list[du.Node]) -> list[dict] | None:
    """All children must convert; one failure poisons the sequence."""
    out = []
    for child in children:
        converted = _convert_block(child)
        if converted is None:
            return None
        out.append(converted)
    return out if out else None


def text_to_view(text: str) -> dict | None:
    """Parse an isolated rst fragment into a view tree (or None if it doesn't
    map onto supported view types). Shared by enrichment and by the
    serializer's verify-reparse loop (rstkit.verify)."""
    if not text.strip():
        return None
    document = _parse_fragment(text)
    if document is None:
        return None
    body = list(document.children)
    # comments (including stubbed directives glued into this block as
    # indented continuations) and parser messages make the fragment
    # unrepresentable — poison, never drop (see _convert_block docstring)
    if any(isinstance(c, (du.system_message, du.comment)) for c in body):
        return None
    if len(body) == 1:
        return _convert_block(body[0])
    if len(body) > 1:
        children = _convert_all_or_none(body)
        if children is None:
            return None
        return {"type": "block_group", "children": children}
    return None


def title_to_view(title: str) -> dict | None:
    """Parse a heading's title text into a heading_title view (inline marks)."""
    if not title.strip():
        return None
    document = _parse_fragment(title)
    if document is None or not document.children:
        return None
    first = document.children[0]
    if isinstance(first, du.paragraph):
        return {"type": "heading_title", "children": _convert_inline_children(first)}
    return None


def enrich_text_node(node: EdNode) -> None:
    """Populate node.view in place; leaves the node untouched on any failure
    or unrecognized shape (frontend falls back to plain raw_source display)."""
    if node.type != "text":
        return
    view = text_to_view(node.raw_source)
    if view is not None:
        node.view = view


def enrich_heading_node(node: EdNode) -> None:
    """Parse just the heading's title text for inline marks (rare, but a
    heading like ``**Bold** Title`` should still render bold)."""
    if node.type != "heading":
        return
    view = title_to_view(node.attrs.get("title", ""))
    if view is not None:
        node.view = view


def enrich_nodes(nodes: list[EdNode]) -> None:
    """Mutate `nodes` in place, adding best-effort `view` trees. Safe to call
    on any EdDoc.nodes list; never raises."""
    for node in nodes:
        try:
            if node.type == "text":
                enrich_text_node(node)
            elif node.type == "heading":
                enrich_heading_node(node)
        except Exception:
            node.view = None
