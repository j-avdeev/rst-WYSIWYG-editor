"""TOC builder + reorder/remove/add endpoints + toctree preview rendering."""

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app
from rstkit.store import LocalGitStore

INDEX = (
    "Главная\n"
    "=======\n"
    "\n"
    ".. toctree::\n"
    "   :maxdepth: 2\n"
    "   :caption: Разделы\n"
    "\n"
    "   intro\n"
    "   Специальное имя <guide/setup>\n"
    "   guide/index\n"
)

GUIDE_INDEX = (
    "Руководство\n"
    "===========\n"
    "\n"
    ".. toctree::\n"
    "\n"
    "   advanced\n"
    "   /intro\n"
)


@pytest.fixture()
def workspace(tmp_path):
    docs = tmp_path / "docs"
    (docs / "guide").mkdir(parents=True)
    (docs / "conf.py").write_text('master_doc = "index"\n', encoding="utf-8")
    (docs / "index.rst").write_text(INDEX, encoding="utf-8")
    (docs / "intro.rst").write_text("Введение\n========\n\nТекст.\n", encoding="utf-8")
    (docs / "guide" / "setup.rst").write_text("Установка\n=========\n", encoding="utf-8")
    (docs / "guide" / "index.rst").write_text(GUIDE_INDEX, encoding="utf-8")
    (docs / "guide" / "advanced.rst").write_text("Продвинутое\n===========\n", encoding="utf-8")
    (docs / "orphan.rst").write_text("Сирота\n======\n", encoding="utf-8")
    app.dependency_overrides[get_store] = lambda: LocalGitStore(docs)
    client = TestClient(app)
    yield docs, client
    app.dependency_overrides.clear()


def test_toc_tree_titles_and_nesting(workspace):
    _, client = workspace
    toc = client.get("/api/toc").json()
    assert toc["master"] == "index"
    tree = toc["tree"]
    assert tree["title"] == "Главная"

    children = tree["children"]
    assert [c["docname"] for c in children] == ["intro", "guide/setup", "guide/index"]
    assert children[0]["title"] == "Введение"          # resolved first heading
    assert children[1]["title"] == "Специальное имя"    # explicit "Title <doc>"
    assert children[2]["title"] == "Руководство"

    nested = children[2]["children"]
    assert [c["docname"] for c in nested] == ["guide/advanced", "intro"]
    assert nested[1]["docname"] == "intro"  # /absolute entry resolved
    # cycle guard: intro was already visited, so it has no re-expanded children
    assert nested[1]["children"] == []

    # provenance points at the exact editable location
    src = children[1]["source"]
    assert src == {"file": "index.rst", "toctree_index": 0, "position": 1}


def test_toc_orphans_detected(workspace):
    _, client = workspace
    toc = client.get("/api/toc").json()
    assert [o["docname"] for o in toc["orphans"]] == ["orphan"]
    assert toc["orphans"][0]["title"] == "Сирота"


def test_toc_reorder_moves_only_entry_lines(workspace):
    docs, client = workspace
    before = (docs / "index.rst").read_text(encoding="utf-8")
    r = client.post(
        "/api/toc/reorder",
        json={"file": "index.rst", "toctree_index": 0, "from_pos": 2, "to_pos": 0},
    )
    assert r.status_code == 200
    after = (docs / "index.rst").read_text(encoding="utf-8")

    assert after.index("guide/index") < after.index("intro")
    # options/caption untouched, line count identical
    assert ":caption: Разделы" in after
    assert len(after.splitlines()) == len(before.splitlines())
    # and the API response reflects the new order
    order = [c["docname"] for c in r.json()["tree"]["children"]]
    assert order == ["guide/index", "guide/advanced", "intro", "guide/setup"] or order[0] == "guide/index"


def test_toc_remove_entry(workspace):
    docs, client = workspace
    r = client.post(
        "/api/toc/remove",
        json={"file": "index.rst", "toctree_index": 0, "position": 1},
    )
    assert r.status_code == 200
    after = (docs / "index.rst").read_text(encoding="utf-8")
    assert "guide/setup" not in after
    assert "intro" in after
    # setup is now an orphan
    assert "guide/setup" in [o["docname"] for o in r.json()["orphans"]]


def test_toc_add_orphan_entry(workspace):
    docs, client = workspace
    r = client.post(
        "/api/toc/entry",
        json={"index_file": "index.rst", "doc_path": "orphan.rst"},
    )
    assert r.status_code == 200
    assert "   orphan" in (docs / "index.rst").read_text(encoding="utf-8")
    assert r.json()["orphans"] == []


def test_preview_renders_toctree_as_nav_box(workspace):
    _, client = workspace
    payload = client.get("/api/doc/index.rst").json()
    blocks = [{"op": "raw", "raw": n["raw_source"]} for n in payload["doc"]["nodes"]]
    r = client.post("/api/preview", json={"path": "index.rst", "blocks": blocks})
    html = r.json()["html"]
    assert "toctree-box" in html
    assert "Введение" in html            # resolved title, not just docname
    assert "Специальное имя" in html     # explicit title
    assert "Разделы" in html             # caption shown