from rstkit.inline import enrich_nodes
from rstkit.parse import parse_rst
from rstkit.pmbridge import pm_from_view
from rstkit.tables import csv_table_to_view
from rstkit.verify import serialize_and_verify_block


CSV_TABLE = (
    '.. csv-table:: **Components**\n'
    '   :header: "No","Component", "Icon"\n'
    '   :widths: 10, 30, 20\n'
    '\n'
    '   "1","`Bus <Object/Bus.html>`_", "|Bus|"\n'
    '   "2","Plain", "two"\n'
)


def test_csv_table_enrichment_parses_header_rows_and_inline_cells():
    doc = parse_rst(CSV_TABLE.encode("utf-8"), check_health=False)
    enrich_nodes(doc.nodes)
    table = doc.nodes[0].view

    assert table is not None
    assert table["type"] == "csv_table"
    assert table["caption"] == "**Components**"
    assert [c["text"] for c in table["header"]["cells"]] == ["No", "Component", "Icon"]

    link_cell = table["rows"][0]["cells"][1]
    assert link_cell["children"][0]["type"] == "link"
    assert link_cell["children"][0]["href"] == "Object/Bus.html"

    subst_cell = table["rows"][0]["cells"][2]
    assert subst_cell["children"][0]["type"] == "subst_ref"
    assert subst_cell["children"][0]["name"] == "Bus"


def test_csv_table_clean_pm_serializes_to_original_text():
    view = csv_table_to_view(CSV_TABLE)
    pm = pm_from_view(view)

    assert serialize_and_verify_block(pm) == CSV_TABLE.rstrip("\n")


def test_csv_table_dirty_cell_preserves_neighboring_raw_tokens():
    view = csv_table_to_view(CSV_TABLE)
    pm = pm_from_view(view)
    # First body row, second cell.
    pm["content"][1]["content"][1]["content"][0]["content"] = [
        {"type": "text", "text": "Edited"}
    ]

    out = serialize_and_verify_block(pm)

    assert '   "1","Edited", "|Bus|"' in out
    assert '   "2","Plain", "two"' in out
    assert '   :header: "No","Component", "Icon"' in out


def _pm_cell(text: str, type_: str = "table_cell"):
    return {
        "type": type_,
        "attrs": {},
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def test_csv_table_added_row_serializes_without_disturbing_clean_rows():
    view = csv_table_to_view(CSV_TABLE)
    pm = pm_from_view(view)
    pm["content"].append(
        {
            "type": "table_row",
            "attrs": {},
            "content": [_pm_cell("3"), _pm_cell("New"), _pm_cell("three")],
        }
    )

    out = serialize_and_verify_block(pm)

    assert '   "1","`Bus <Object/Bus.html>`_", "|Bus|"' in out
    assert '   "2","Plain", "two"' in out
    assert '   "3","New","three"' in out


def test_csv_table_deleted_row_omits_only_that_row():
    view = csv_table_to_view(CSV_TABLE)
    pm = pm_from_view(view)
    del pm["content"][2]

    out = serialize_and_verify_block(pm)

    assert '   "1","`Bus <Object/Bus.html>`_", "|Bus|"' in out
    assert '   "2","Plain", "two"' not in out


def test_csv_table_added_column_reserializes_each_affected_row():
    view = csv_table_to_view(CSV_TABLE)
    pm = pm_from_view(view)
    pm["content"][0]["content"].append(_pm_cell("Extra", "table_header"))
    pm["content"][1]["content"].append(_pm_cell("one-extra"))
    pm["content"][2]["content"].append(_pm_cell("two-extra"))

    out = serialize_and_verify_block(pm)

    assert '   :header: "No","Component", "Icon","Extra"' in out
    assert '   "1","`Bus <Object/Bus.html>`_", "|Bus|","one-extra"' in out
    assert '   "2","Plain", "two","two-extra"' in out


def test_csv_table_deleted_column_reserializes_even_when_remaining_cells_are_clean():
    view = csv_table_to_view(CSV_TABLE)
    pm = pm_from_view(view)
    for row in pm["content"]:
        del row["content"][1]

    out = serialize_and_verify_block(pm)

    assert '   :header: "No", "Icon"' in out
    assert '   "1", "|Bus|"' in out
    assert '   "2", "two"' in out
    assert "Object/Bus.html" not in out


def test_csv_table_file_option_stays_opaque():
    raw = (
        ".. csv-table:: External\n"
        "   :file: data.csv\n"
        "\n"
    )

    assert csv_table_to_view(raw) is None
