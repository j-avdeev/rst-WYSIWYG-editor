"""Options-editing semantics for csv-tables (backend side of the popover):
- editing an option's value clears its raw -> only that line re-emits
- untouched options keep their raw line byte-identical, order preserved
- changing the CSV dialect forces full table re-serialization (raw rows
  were captured under the old dialect and must not survive)
- caption edits rebuild the directive line
"""

from rstkit.pmbridge import pm_from_view
from rstkit.tables import csv_table_to_view
from rstkit.verify import serialize_and_verify_block

CSV_TABLE = (
    ".. csv-table:: Sample\n"
    '   :header: "No","Name"\n'
    "   :widths:  10,  30\n"
    "   :align: left\n"
    "\n"
    '   "1","one, and"\n'
    '   "2","two"\n'
)


def _pm():
    return pm_from_view(csv_table_to_view(CSV_TABLE))


def test_editing_one_option_value_reemits_only_that_line():
    pm = _pm()
    for opt in pm["attrs"]["csv"]["options"]:
        if opt["name"] == "widths":
            opt["value"] = "20, 40"
            opt["raw"] = ""  # what the popover does on value change

    out = serialize_and_verify_block(pm)
    lines = out.split("\n")
    assert lines[0] == ".. csv-table:: Sample"
    assert lines[1] == '   :header: "No","Name"'  # untouched raw kept
    assert lines[2] == "   :widths: 20, 40"  # re-emitted, canonical spacing
    assert lines[3] == "   :align: left"  # untouched raw kept, order preserved
    assert '   "1","one, and"' in out  # body rows untouched


def test_adding_an_option_appends_it():
    pm = _pm()
    pm["attrs"]["csv"]["options"].append({"name": "stub-columns", "value": "1", "raw": ""})
    out = serialize_and_verify_block(pm)
    assert "   :stub-columns: 1" in out


def test_removing_an_option_drops_its_line():
    pm = _pm()
    pm["attrs"]["csv"]["options"] = [
        o for o in pm["attrs"]["csv"]["options"] if o["name"] != "align"
    ]
    out = serialize_and_verify_block(pm)
    assert ":align:" not in out


def test_caption_edit_rebuilds_directive_line():
    pm = _pm()
    pm["attrs"]["csv"]["caption"] = "Новая подпись"
    pm["attrs"]["csv"]["directive"] = ""  # what the popover does on caption change
    out = serialize_and_verify_block(pm)
    assert out.split("\n")[0] == ".. csv-table:: Новая подпись"


def test_dialect_change_forces_full_reserialization():
    pm = _pm()
    pm["attrs"]["csv"]["options"].append({"name": "delim", "value": ";", "raw": ""})
    out = serialize_and_verify_block(pm)
    # the cell containing ", and" needed quoting under "," but not under ";" —
    # and raw rows written under the old dialect must all be gone
    assert "   :delim: ;" in out
    assert '"1","one, and"' not in out  # old-dialect raw did not survive
    assert '1;one, and' in out or '"1";"one, and"' in out


def test_dialect_change_verifies_round_trip():
    pm = _pm()
    pm["attrs"]["csv"]["options"].append({"name": "quote", "value": "'", "raw": ""})
    out = serialize_and_verify_block(pm)  # verify-reparse inside must pass
    reparsed = csv_table_to_view(out + "\n")
    assert reparsed is not None
    assert [c["text"] for c in reparsed["rows"][0]["cells"]] == ["1", "one, and"]
