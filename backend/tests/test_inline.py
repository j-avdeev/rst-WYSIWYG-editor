"""Tests for the best-effort rendering enrichment (inline.py).

These only assert on `view` — enrichment must never affect `raw_source`,
`span`, or round-trip fidelity, which test_roundtrip.py / test_corpus_
fixtures.py already cover independently.
"""

from rstkit.inline import enrich_nodes
from rstkit.parse import parse_rst


def _enrich(data: bytes):
    doc = parse_rst(data, check_health=False)
    enrich_nodes(doc.nodes)
    return doc


def _views(doc):
    return [n.view for n in doc.nodes]


def test_simple_paragraph():
    doc = _enrich(b"A simple paragraph.\n")
    view = doc.nodes[0].view
    assert view["type"] == "paragraph"
    assert view["children"] == [{"type": "text", "text": "A simple paragraph."}]


def test_inline_marks():
    doc = _enrich(b"Some *emphasis* and **strong** and ``literal`` text.\n")
    view = doc.nodes[0].view
    types = [c["type"] for c in view["children"]]
    assert "em" in types
    assert "strong" in types
    assert "literal" in types


def test_hyperlink():
    doc = _enrich(b"See `example <https://example.com>`_ for more.\n")
    view = doc.nodes[0].view
    link = next(c for c in view["children"] if c["type"] == "link")
    assert link["href"] == "https://example.com"


def test_substitution_reference():
    doc = _enrich(b"Uses |Fluid| icon.\n")
    view = doc.nodes[0].view
    ref = next(c for c in view["children"] if c["type"] == "subst_ref")
    assert ref["name"] == "Fluid"


def test_bullet_list():
    doc = _enrich(b"- item one\n\n- item two\n")
    # scanner may split into two top-level "text" blocks (see parse.py);
    # each still enriches to a bullet_list with one item.
    for node in doc.nodes:
        if node.type != "text":
            continue
        assert node.view is not None
        assert node.view["type"] == "bullet_list"
        assert len(node.view["children"]) >= 1
        assert node.view["children"][0]["type"] == "list_item"


def test_literal_block():
    # "Example::" + indented body isolate-parses to TWO docutils nodes
    # (paragraph "Example:" + literal_block) -> wrapped as a block_group.
    doc = _enrich(b"Example::\n\n   code here\n   more code\n")
    text_nodes = [n for n in doc.nodes if n.type == "text"]
    assert len(text_nodes) == 1
    view = text_nodes[0].view
    assert view["type"] == "block_group"
    kinds = [c["type"] for c in view["children"]]
    assert "literal_block" in kinds


def test_standalone_literal_block():
    doc = _enrich(b"::\n\n   code only\n")
    node = next(n for n in doc.nodes if n.type == "text")
    assert node.view["type"] == "literal_block"
    assert "code only" in node.view["text"]


def test_heading_title_extracted():
    doc = _enrich(b"Title\n=====\n\nBody.\n")
    heading = doc.nodes[0]
    assert heading.type == "heading"
    assert heading.attrs["title"] == "Title"


def test_heading_view_with_inline_marks():
    doc = _enrich(b"**Bold** Title\n==============\n\nBody.\n")
    heading = doc.nodes[0]
    assert heading.view is not None
    assert heading.view["type"] == "heading_title"
    assert any(c["type"] == "strong" for c in heading.view["children"])


def test_never_raises_on_garbage():
    # Malformed / ambiguous fragments must degrade to view=None, not raise.
    tricky = [
        b"unbalanced *emphasis\n",
        b"|undefined-subst| reference\n",
        b":unknown-role:`text`\n",
        b"\x00binary junk\n",
    ]
    for data in tricky:
        doc = _enrich(data)  # must not raise


def test_directive_and_comment_nodes_untouched():
    doc = _enrich(b".. note::\n\n   Body.\n\n.. a comment\n")
    for node in doc.nodes:
        if node.type in ("directive", "comment"):
            assert node.view is None
