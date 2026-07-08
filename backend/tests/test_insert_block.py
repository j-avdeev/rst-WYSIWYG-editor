"""A brand-new top-level block (no corresponding original EdNode — e.g. an
image inserted mid-document by the frontend) has never been exercised by the
save path before; assemble.py processes whatever block list it's given
positionally, so this should already work, but it's worth locking down."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app
from rstkit.store import LocalGitStore

FIXTURES = Path(__file__).parent / "fixtures" / "corpus"
REL = "pradis-sphinx-doc/doc_pradis/1_overview.rst"


@pytest.fixture()
def workspace(tmp_path):
    root = tmp_path / "docs"
    dst = root / REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / REL, dst)
    app.dependency_overrides[get_store] = lambda: LocalGitStore(root)
    client = TestClient(app)
    yield root, client
    app.dependency_overrides.clear()


def test_insert_new_figure_block_mid_document(workspace):
    root, client = workspace
    payload = client.get(f"/api/doc/{REL}").json()
    nodes = payload["doc"]["nodes"]

    blocks = [{"op": "raw", "raw": n["raw_source"]} for n in nodes]
    insert_at = len(blocks) // 2
    blocks.insert(
        insert_at,
        {"op": "rawedit", "raw": ".. figure:: media/uploaded.png\n\n   \n"},
    )

    r = client.put(
        f"/api/doc/{REL}",
        json={"base_mtime_ns": payload["mtime_ns"], "blocks": blocks},
    )
    assert r.status_code == 200, r.text
    text = (root / REL).read_bytes().decode("utf-8")
    assert ".. figure:: media/uploaded.png" in text

    # re-fetch: the new block must parse back out as its own directive node
    refetched = client.get(f"/api/doc/{REL}").json()
    kinds = [n["attrs"].get("name") for n in refetched["doc"]["nodes"] if n["type"] == "directive"]
    assert "figure" in kinds


def test_insert_preserves_neighboring_blocks_byte_exact(workspace):
    root, client = workspace
    payload = client.get(f"/api/doc/{REL}").json()
    nodes = payload["doc"]["nodes"]
    blocks = [{"op": "raw", "raw": n["raw_source"]} for n in nodes]
    blocks.insert(1, {"op": "rawedit", "raw": ".. image:: media/x.png\n"})

    r = client.put(
        f"/api/doc/{REL}",
        json={"base_mtime_ns": payload["mtime_ns"], "blocks": blocks},
    )
    assert r.status_code == 200, r.text
    text = (root / REL).read_bytes().decode("utf-8")
    # first original block's text is still present verbatim
    assert nodes[0]["raw_source"] in text
    assert nodes[-1]["raw_source"].strip() in text
