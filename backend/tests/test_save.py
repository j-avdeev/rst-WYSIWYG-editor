"""Save-path tests: dirty-node serialization end-to-end through the API,
against throwaway copies of real corpus fixtures (never the originals)."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app
from rstkit.store import LocalGitStore

FIXTURES = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture()
def workspace(tmp_path):
    """A temp copy of a few real fixture files, served by the app."""
    root = tmp_path / "docs"
    for rel in [
        "pradis-sphinx-doc/index.rst",
        "pradis-sphinx-doc/doc_pradis/1_overview.rst",
        "pradis-sphinx-doc/doc_sprav/user_modules/Hydro/Model/QTR.rst",
    ]:
        src = FIXTURES / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    app.dependency_overrides[get_store] = lambda: LocalGitStore(root)
    client = TestClient(app)
    yield root, client
    app.dependency_overrides.clear()


def _get(client, rel):
    r = client.get(f"/api/doc/{rel}")
    assert r.status_code == 200
    return r.json()


def _blocks_all_raw(payload):
    return [{"op": "raw", "raw": n["raw_source"]} for n in payload["doc"]["nodes"]]


REL = "pradis-sphinx-doc/doc_pradis/1_overview.rst"


def test_save_no_edits_is_byte_identical(workspace):
    root, client = workspace
    before = (root / REL).read_bytes()
    payload = _get(client, REL)
    r = client.put(
        f"/api/doc/{REL}",
        json={"base_mtime_ns": payload["mtime_ns"], "blocks": _blocks_all_raw(payload)},
    )
    assert r.status_code == 200, r.text
    assert (root / REL).read_bytes() == before


def test_save_stale_mtime_conflicts(workspace):
    root, client = workspace
    payload = _get(client, REL)
    r = client.put(
        f"/api/doc/{REL}",
        json={"base_mtime_ns": payload["mtime_ns"] - 1, "blocks": _blocks_all_raw(payload)},
    )
    assert r.status_code == 409


def test_save_typo_edit_changes_exactly_one_block(workspace):
    root, client = workspace
    before = (root / REL).read_bytes()
    payload = _get(client, REL)

    # find a paragraph node and simulate an edited PM paragraph
    target = None
    for n in payload["doc"]["nodes"]:
        if n["type"] == "text" and n["view"] and n["view"]["type"] == "paragraph":
            target = n
            break
    assert target is not None, "fixture has no editable paragraph"

    blocks = []
    for n in payload["doc"]["nodes"]:
        if n["id"] == target["id"]:
            blocks.append(
                {
                    "op": "node",
                    "pm": {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Отредактированный абзац с опечаткой."}
                        ],
                    },
                }
            )
        else:
            blocks.append({"op": "raw", "raw": n["raw_source"]})

    r = client.put(
        f"/api/doc/{REL}",
        json={"base_mtime_ns": payload["mtime_ns"], "blocks": blocks},
    )
    assert r.status_code == 200, r.text

    after = (root / REL).read_bytes()
    assert after != before
    assert "Отредактированный абзац с опечаткой." in after.decode("utf-8")

    # everything before and after the edited block is byte-identical
    before_text = before.decode("utf-8")
    prefix = "".join(
        n["raw_source"] for n in payload["doc"]["nodes"][: payload["doc"]["nodes"].index(target)]
    )
    assert after.decode("utf-8").startswith(prefix)
    suffix_nodes = payload["doc"]["nodes"][payload["doc"]["nodes"].index(target) + 1 :]
    suffix = "".join(n["raw_source"] for n in suffix_nodes)
    if suffix:
        assert after.decode("utf-8").endswith(suffix)
    assert before_text.startswith(prefix)  # sanity


def test_save_rejects_unserializable_block(workspace):
    root, client = workspace
    before = (root / REL).read_bytes()
    payload = _get(client, REL)
    blocks = _blocks_all_raw(payload)
    blocks[0] = {"op": "node", "pm": {"type": "paragraph", "content": []}}  # empty
    r = client.put(
        f"/api/doc/{REL}", json={"base_mtime_ns": payload["mtime_ns"], "blocks": blocks}
    )
    assert r.status_code == 422
    assert (root / REL).read_bytes() == before  # file untouched


def test_save_rawedit_opaque_block(workspace):
    root, client = workspace
    payload = _get(client, REL)
    blocks = []
    edited = False
    for n in payload["doc"]["nodes"]:
        if not edited and n["type"] == "directive":
            blocks.append({"op": "rawedit", "raw": ".. note::\n\n   Edited opaque body.\n"})
            edited = True
        else:
            blocks.append({"op": "raw", "raw": n["raw_source"]})
    if not edited:
        pytest.skip("fixture has no directive block")
    r = client.put(
        f"/api/doc/{REL}", json={"base_mtime_ns": payload["mtime_ns"], "blocks": blocks}
    )
    assert r.status_code == 200, r.text
    text = (root / REL).read_bytes().decode("utf-8")
    assert "Edited opaque body." in text


def test_save_heading_edit_preserves_adornment_style(workspace):
    root, client = workspace
    payload = _get(client, REL)
    heading = next(n for n in payload["doc"]["nodes"] if n["type"] == "heading")
    blocks = []
    for n in payload["doc"]["nodes"]:
        if n["id"] == heading["id"]:
            blocks.append(
                {
                    "op": "node",
                    "pm": {
                        "type": "heading",
                        "attrs": {
                            "underline": heading["attrs"]["underline"],
                            "overline": heading["attrs"]["overline"],
                        },
                        "content": [{"type": "text", "text": "Новый заголовок раздела"}],
                    },
                }
            )
        else:
            blocks.append({"op": "raw", "raw": n["raw_source"]})
    r = client.put(
        f"/api/doc/{REL}", json={"base_mtime_ns": payload["mtime_ns"], "blocks": blocks}
    )
    assert r.status_code == 200, r.text
    text = (root / REL).read_bytes().decode("utf-8")
    assert "Новый заголовок раздела" in text
    char = heading["attrs"]["underline"]
    assert char * len("Новый заголовок раздела") in text


def test_preview_endpoint(workspace):
    root, client = workspace
    payload = _get(client, REL)
    blocks = _blocks_all_raw(payload)
    r = client.post("/api/preview", json={"path": REL, "blocks": blocks})
    assert r.status_code == 200
    body = r.json()
    assert "<" in body["html"]
    assert body["text"].strip()
    assert len(body["blocks"]) == len(blocks)
    assert not any(b["dirty"] for b in body["blocks"])


def test_preview_with_dirty_block_marks_it(workspace):
    root, client = workspace
    payload = _get(client, REL)
    blocks = _blocks_all_raw(payload)
    blocks[-1] = {
        "op": "node",
        "pm": {"type": "paragraph", "content": [{"type": "text", "text": "Предпросмотр."}]},
    }
    r = client.post("/api/preview", json={"path": REL, "blocks": blocks})
    assert r.status_code == 200
    body = r.json()
    assert body["blocks"][-1]["dirty"] is True
    assert "Предпросмотр." in body["text"]
    assert "Предпросмотр." in body["html"]
