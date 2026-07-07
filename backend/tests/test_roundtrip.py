"""Round-trip identity and block-scanner tests on tricky rst snippets."""

import pytest

from rstkit.parse import parse_rst, verify_partition
from rstkit.serialize import serialize


def roundtrip(data: bytes) -> bytes:
    doc = parse_rst(data, check_health=False)
    verify_partition(doc.nodes, len(data.decode(doc.encoding).splitlines(keepends=True)) if not doc.bom else len(data[3:].decode(doc.encoding).splitlines(keepends=True)))
    return serialize(doc)


IDENTITY_CASES = {
    "simple": b"Title\n=====\n\nA paragraph.\n",
    "cyrillic_lf": "Заголовок\n=========\n\nАбзац текста на русском.\n".encode("utf-8"),
    "cyrillic_crlf": "Заголовок\r\n=========\r\n\r\nАбзац.\r\n".encode("utf-8"),
    "bom": b"\xef\xbb\xbfTitle\n=====\n\nText.\n",
    "no_final_newline": b"Title\n=====\n\nNo newline at end",
    "mixed_eol": b"one\r\n\ntwo\nthree\r\n",
    "directive_with_options": (
        b".. csv-table:: Caption\n"
        b"   :header: A, B\n"
        b"   :widths: 10, 20\n"
        b"\n"
        b"   1, 2\n"
        b"   3, 4\n"
        b"\n"
        b"After.\n"
    ),
    "directive_trailing_blanks": b".. note::\n\n   Body.\n\n\n\nNext paragraph.\n",
    "substitution_def": b".. |Fluid| image:: /_static/fluid.png\n\nUses |Fluid| icon.\n",
    "overline_heading": b"#########\n Chapter\n#########\n\nText.\n",
    "transition": b"Before.\n\n----\n\nAfter.\n",
    "comment_block": b".. this is a comment\n   continued here\n\nText.\n",
    "hyperlink_target": b".. _my-target:\n\nParagraph.\n",
    "literal_block": b"Example::\n\n   indented code\n   more code\n\nAfter.\n",
    "list_with_blanks": b"- item one\n\n- item two\n\n  continuation\n\nAfter.\n",
    "stacked_directives": b".. a::\n.. b::\n\ntext\n",
    "leading_blanks": b"\n\n\nTitle\n=====\n",
    "only_blanks": b"\n\n\n",
    "empty": b"",
    "math": (
        b".. math::\n"
        b"\n"
        b"   e^{i\\pi} + 1 = 0\n"
        b"\n"
        b"Inline :math:`x^2` too.\n"
    ),
    "include": b".. include:: ../common/defs.rst\n\nText.\n",
    "field_list_docinfo": b":orphan:\n\nTitle\n=====\n",
    "grid_table": (
        b"+-----+-----+\n"
        b"| a   | b   |\n"
        b"+-----+-----+\n"
        b"\n"
        b"After.\n"
    ),
    "windows_1251": "Текст в cp1251.\n".encode("cp1251"),
}


@pytest.mark.parametrize("name", IDENTITY_CASES)
def test_identity(name):
    data = IDENTITY_CASES[name]
    assert roundtrip(data) == data


def test_classification_basic():
    doc = parse_rst(
        b"Title\n=====\n\nPara.\n\n.. image:: x.png\n\n.. just a comment\n",
        check_health=False,
    )
    types = [n.type for n in doc.nodes]
    assert types == ["heading", "text", "directive", "comment"]
    assert doc.nodes[0].attrs["underline"] == "="
    assert doc.nodes[2].attrs["name"] == "image"


def test_blank_lines_attach_to_preceding_block():
    doc = parse_rst(b"One.\n\n\nTwo.\n", check_health=False)
    assert doc.nodes[0].raw_source == "One.\n\n\n"
    assert doc.nodes[1].raw_source == "Two.\n"


def test_eol_and_encoding_metadata():
    doc = parse_rst("Привет\r\n".encode("utf-8"), check_health=False)
    assert doc.eol == "crlf"
    assert doc.encoding == "utf-8"
    doc = parse_rst("Привет\n".encode("cp1251"), check_health=False)
    assert doc.encoding == "cp1251"
    assert doc.warnings


def test_docutils_health_runs():
    doc = parse_rst(b"Title\n=====\n\nSome *text*.\n", check_health=True)
    assert doc.parse_errors == 0


def test_unknown_directive_is_not_a_parse_error():
    doc = parse_rst(
        b".. totally-unknown-directive::\n   :weird-option: 1\n\n   content\n",
        check_health=True,
    )
    assert doc.parse_errors == 0
