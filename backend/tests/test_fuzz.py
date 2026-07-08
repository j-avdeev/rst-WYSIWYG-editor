"""Property/fuzz tests for the serializer's CSV-quoting x rst-escaping edges.

The safety contract under test: `serialize_and_verify_block` either returns
rst text that re-parses to exactly what the editor showed (verify-reparse
proves it), or raises SerializeError — a clean save rejection. A VerifyError
here means the serializer *produced wrong output* and only the safety net
caught it; every such case is a serializer bug these tests exist to find,
so VerifyError fails the test while SerializeError is an accepted outcome.
"""

from hypothesis import assume, given, settings, strategies as st

from rstkit.pmserialize import SerializeError
from rstkit.tables import csv_table_to_view
from rstkit.pmbridge import pm_from_view
from rstkit.verify import VerifyError, serialize_and_verify_block

# Text a user could realistically type or paste into a cell/paragraph:
# Latin + Cyrillic + digits + punctuation incl. every rst/CSV special.
_CHARS = (
    "abcXYZ абвГДЕ 0123456789"
    "*_`|\\\"',;:.<>()[]{}#+-=!?/&%$@~^«»—"
)
cell_text = st.text(alphabet=_CHARS, min_size=0, max_size=40)
para_text = st.text(alphabet=_CHARS, min_size=1, max_size=80)

MARKS = st.sampled_from([None, "strong", "em", "code"])


def _pm_paragraph(text: str, mark: str | None):
    node: dict = {"type": "text", "text": text}
    if mark:
        node["marks"] = [{"type": mark}]
    return {"type": "paragraph", "content": [node]}


def _check(pm) -> str | None:
    """Returns serialized text on success, None on accepted rejection."""
    try:
        return serialize_and_verify_block(pm)
    except SerializeError:
        return None
    except VerifyError as exc:
        raise AssertionError(
            f"serializer produced wrong output (caught only by verify): "
            f"{exc}\nexpected={exc.expected!r}\nactual={exc.actual!r}"
        ) from exc


@settings(max_examples=300, deadline=None)
@given(text=para_text, mark=MARKS)
def test_fuzz_paragraph_roundtrip(text: str, mark: str | None):
    assume(text.strip())
    _check(_pm_paragraph(text, mark))


def _pm_csv_table(cells: list[list[str]], delimiter: str, quotechar: str):
    """A fully-dirty table (no raw attrs), as after heavy editing. The CSV
    dialect is declared through real option lines — the serializer derives
    the effective dialect from those, exactly like the re-parser does."""
    options = []
    if delimiter != ",":
        options.append({"name": "delim", "value": delimiter, "raw": f"   :delim: {delimiter}"})
    if quotechar != '"':
        options.append({"name": "quote", "value": quotechar, "raw": f"   :quote: {quotechar}"})
    rows = []
    for row_cells in cells:
        rows.append(
            {
                "type": "table_row",
                "attrs": {},
                "content": [
                    {
                        "type": "table_cell",
                        "attrs": {},
                        "content": [
                            {
                                "type": "paragraph",
                                "content": (
                                    [{"type": "text", "text": t}] if t else []
                                ),
                            }
                        ],
                    }
                    for t in row_cells
                ],
            }
        )
    return {
        "type": "table",
        "attrs": {
            "csv": {
                "kind": "csv_table",
                "caption": "",
                "directive": ".. csv-table::",
                "indent": "   ",
                "delimiter": delimiter,
                "quote": quotechar,
                "options": options,
                "hasHeader": False,
            }
        },
        "content": rows,
    }


@settings(max_examples=300, deadline=None)
@given(
    cells=st.lists(
        st.lists(cell_text, min_size=1, max_size=4),
        min_size=1,
        max_size=4,
    ).map(lambda rows: [row + [""] * (max(map(len, rows)) - len(row)) for row in rows]),
    delimiter=st.sampled_from([",", ";"]),
    quotechar=st.sampled_from(['"', "'"]),
)
def test_fuzz_csv_table_roundtrip(cells, delimiter, quotechar):
    # whitespace-only (but non-empty) cell content is a documented rejection:
    # such cells can't re-parse as inline fragments, so saves are refused
    # rather than silently normalized
    assume(all(t == "" or t.strip() for row in cells for t in row))
    _check(_pm_csv_table(cells, delimiter, quotechar))


BASE_TABLE = (
    ".. csv-table:: Sample\n"
    '   :header: "No","Name","Icon"\n'
    "   :widths: 10, 30, 20\n"
    "\n"
    '   "1","`Bus <Object/Bus.html>`_", "|Bus|"\n'
    '   "2","Plain, with comma", "two"\n'
    '   "3","**bold** text", "three"\n'
)


@settings(max_examples=200, deadline=None)
@given(
    row_idx=st.integers(min_value=0, max_value=2),
    col_idx=st.integers(min_value=0, max_value=2),
    new_text=cell_text,
)
def test_fuzz_single_cell_edit_changes_exactly_one_line(row_idx, col_idx, new_text):
    assume(new_text == "" or new_text.strip())

    view = csv_table_to_view(BASE_TABLE)
    clean_pm = pm_from_view(view)
    clean_out = serialize_and_verify_block(clean_pm)

    dirty_pm = pm_from_view(view)
    # body rows sit after the header row in PM content
    cell = dirty_pm["content"][1 + row_idx]["content"][col_idx]
    cell["content"][0]["content"] = (
        [{"type": "text", "text": new_text}] if new_text else []
    )

    out = _check(dirty_pm)
    if out is None:
        return  # accepted rejection

    clean_lines = clean_out.split("\n")
    dirty_lines = out.split("\n")
    assert len(clean_lines) == len(dirty_lines), "edit must not add/remove lines"
    diffs = [
        i for i, (a, b) in enumerate(zip(clean_lines, dirty_lines)) if a != b
    ]
    edited_line_idx = 4 + row_idx  # directive, 2 options, blank, then body rows
    assert diffs == [] or diffs == [edited_line_idx], (
        f"edit of row {row_idx} touched lines {diffs}:\n"
        + "\n".join(dirty_lines)
    )
