"""Git endpoints + page creation/rename, on a throwaway git repo whose
layout mirrors PRADIS (store root is a subdirectory of the repo toplevel).
Covers the Phase 5 AC loop: create -> toctree -> edit -> diff -> commit."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app
from app.routers.git import _repo_for
from rstkit.store import LocalGitStore

INDEX = (
    "Разделы\n"
    "=======\n"
    "\n"
    ".. toctree::\n"
    "   :maxdepth: 2\n"
    "\n"
    "   intro\n"
    "   guide/setup\n"
)

INTRO = "Интро\n=====\n\nПервый абзац.\n"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=t@t.local", *args],
        cwd=repo,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout.decode("utf-8", "replace")


@pytest.fixture()
def workspace(tmp_path):
    repo = tmp_path / "repo"
    docs = repo / "docs-src"
    (docs / "guide").mkdir(parents=True)
    (docs / "index.rst").write_text(INDEX, encoding="utf-8")
    (docs / "intro.rst").write_text(INTRO, encoding="utf-8")
    (docs / "guide" / "setup.rst").write_text("Setup\n=====\n\nText.\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")

    app.dependency_overrides[get_store] = lambda: LocalGitStore(docs)
    _repo_for.cache_clear()
    client = TestClient(app)
    yield docs, repo, client
    app.dependency_overrides.clear()
    _repo_for.cache_clear()


def test_status_clean_then_modified(workspace):
    docs, repo, client = workspace
    r = client.get("/api/git/status")
    assert r.status_code == 200
    assert r.json()["branch"] == "main"
    assert r.json()["files"] == []

    (docs / "intro.rst").write_text(INTRO + "Новый абзац.\n", encoding="utf-8")
    files = client.get("/api/git/status").json()["files"]
    assert files == [{"path": "intro.rst", "status": "M"}]


def test_diff_tracked_and_untracked(workspace):
    docs, repo, client = workspace
    (docs / "intro.rst").write_text(INTRO.replace("Первый", "Изменённый"), encoding="utf-8")
    d = client.get("/api/git/diff", params={"path": "intro.rst"}).json()
    assert not d["untracked"]
    assert "-Первый абзац." in d["diff"]
    assert "+Изменённый абзац." in d["diff"]

    (docs / "new.rst").write_text("New\n===\n", encoding="utf-8")
    d = client.get("/api/git/diff", params={"path": "new.rst"}).json()
    assert d["untracked"]
    assert "+New" in d["diff"]


def test_commit_selected_paths_only(workspace):
    docs, repo, client = workspace
    (docs / "intro.rst").write_text(INTRO + "A.\n", encoding="utf-8")
    (docs / "guide" / "setup.rst").write_text("Setup\n=====\n\nChanged.\n", encoding="utf-8")

    r = client.post(
        "/api/git/commit",
        json={"message": "edit intro only", "paths": ["intro.rst"]},
    )
    assert r.status_code == 200, r.text
    assert "edit intro only" in r.json()["head"]

    files = client.get("/api/git/status").json()["files"]
    assert files == [{"path": "guide/setup.rst", "status": "M"}]


def test_commit_requires_message(workspace):
    _, _, client = workspace
    r = client.post("/api/git/commit", json={"message": "  ", "paths": ["intro.rst"]})
    assert r.status_code == 400


def test_discard_tracked_restores_content(workspace):
    docs, repo, client = workspace
    (docs / "intro.rst").write_text("clobbered", encoding="utf-8")
    r = client.post("/api/git/discard", json={"path": "intro.rst"})
    assert r.status_code == 200
    assert (docs / "intro.rst").read_text(encoding="utf-8") == INTRO


def test_discard_untracked_deletes(workspace):
    docs, repo, client = workspace
    (docs / "junk.rst").write_text("x", encoding="utf-8")
    client.post("/api/git/discard", json={"path": "junk.rst"})
    assert not (docs / "junk.rst").exists()


def test_create_page_with_toctree_entry(workspace):
    docs, repo, client = workspace
    r = client.post(
        "/api/files",
        json={"path": "guide/new-page.rst", "title": "Новая страница", "toctree_index": "index.rst"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["toctree_updated"] is True

    body = (docs / "guide" / "new-page.rst").read_bytes().decode("utf-8")
    assert body.startswith("Новая страница\r\n==============\r\n")

    index = (docs / "index.rst").read_text(encoding="utf-8")
    lines = index.splitlines()
    assert "   guide/new-page" in lines
    # existing entries untouched, new entry appended after them
    assert lines.index("   guide/new-page") > lines.index("   guide/setup")


def test_create_page_duplicate_toctree_entry_rejected(workspace):
    docs, repo, client = workspace
    r = client.post(
        "/api/files",
        json={"path": "intro.rst", "title": "X", "toctree_index": "index.rst"},
    )
    assert r.status_code == 409  # file exists

    r = client.post(
        "/api/files",
        json={"path": "intro2.rst", "title": "X", "toctree_index": "index.rst"},
    )
    assert r.status_code == 200
    r = client.post(
        "/api/files",
        json={"path": "intro2.rst", "title": "X", "toctree_index": "index.rst"},
    )
    assert r.status_code == 409


def test_rename_updates_toctree_references_and_preserves_history(workspace):
    docs, repo, client = workspace
    r = client.post(
        "/api/files/rename",
        json={"path": "guide/setup.rst", "new_path": "guide/installation.rst"},
    )
    assert r.status_code == 200, r.text
    assert "index.rst" in r.json()["toctrees_updated"]

    assert not (docs / "guide" / "setup.rst").exists()
    assert (docs / "guide" / "installation.rst").is_file()

    index = (docs / "index.rst").read_text(encoding="utf-8")
    assert "guide/installation" in index
    assert "guide/setup" not in index

    # rename staged as a move (history preserved via git mv)
    status = _git(repo, "status", "--porcelain")
    assert "R " in status or "R" in status.split()[0]


def test_full_phase5_loop(workspace):
    """create -> toctree -> edit (via save API) -> diff -> commit"""
    docs, repo, client = workspace
    r = client.post(
        "/api/files",
        json={"path": "loop.rst", "title": "Цикл", "toctree_index": "index.rst"},
    )
    assert r.status_code == 200

    payload = client.get("/api/doc/loop.rst").json()
    blocks = [{"op": "raw", "raw": n["raw_source"]} for n in payload["doc"]["nodes"]]
    blocks.append(
        {
            "op": "node",
            "pm": {"type": "paragraph", "content": [{"type": "text", "text": "Написано в браузере."}]},
        }
    )
    r = client.put(
        "/api/doc/loop.rst",
        json={"base_mtime_ns": payload["mtime_ns"], "blocks": blocks},
    )
    assert r.status_code == 200, r.text

    d = client.get("/api/git/diff", params={"path": "loop.rst"}).json()
    assert "Написано в браузере." in d["diff"]

    r = client.post(
        "/api/git/commit",
        json={"message": "Новая страница из редактора", "paths": ["loop.rst", "index.rst"]},
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/git/status").json()["files"] == []
