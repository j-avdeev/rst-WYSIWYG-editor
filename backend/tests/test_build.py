"""Sphinx build cycle on a minimal project: start, poll, serve built HTML."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app
from rstkit.store import LocalGitStore

CONF = 'project = "Mini"\nextensions = []\nhtml_theme = "alabaster"\n'
INDEX = "Mini docs\n=========\n\n.. toctree::\n\n   page\n"
PAGE = "Страница\n========\n\nАбзац с **жирным** текстом.\n"


@pytest.fixture()
def workspace(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "conf.py").write_text(CONF, encoding="utf-8")
    (docs / "index.rst").write_text(INDEX, encoding="utf-8")
    (docs / "page.rst").write_text(PAGE, encoding="utf-8")
    app.dependency_overrides[get_store] = lambda: LocalGitStore(docs)
    client = TestClient(app)
    yield docs, client
    app.dependency_overrides.clear()


def _wait_for_build(client, timeout=90.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/api/build/status").json()
        if status["state"] not in ("running",):
            return status
        time.sleep(0.5)
    raise TimeoutError("build did not finish in time")


def test_build_and_serve(workspace):
    docs, client = workspace

    r = client.post("/api/build")
    assert r.status_code == 200
    assert r.json()["state"] in ("running", "succeeded")

    status = _wait_for_build(client)
    assert status["state"] == "succeeded", "\n".join(status["log_tail"])
    assert (docs / "build" / "html" / "page.html").is_file()

    page = client.get("/built/page.html")
    assert page.status_code == 200
    assert "Страница" in page.text
    assert "<strong>жирным</strong>" in page.text

    # relative static assets of the built site resolve too
    css_ref = next(
        (seg for seg in page.text.split('"') if seg.startswith("_static/") and seg.endswith(".css")),
        None,
    )
    assert css_ref is not None
    assert client.get(f"/built/{css_ref}").status_code == 200

    # directory URL falls back to its index.html
    assert client.get("/built/").status_code == 200


def test_built_path_traversal_rejected(workspace):
    docs, client = workspace
    r = client.get("/built/..%2F..%2Fconf.py")
    assert r.status_code in (400, 404)


def test_built_before_build_404s(tmp_path):
    docs = tmp_path / "fresh"
    docs.mkdir()
    (docs / "conf.py").write_text(CONF, encoding="utf-8")
    (docs / "index.rst").write_text(INDEX, encoding="utf-8")
    app.dependency_overrides[get_store] = lambda: LocalGitStore(docs)
    try:
        client = TestClient(app)
        assert client.get("/built/index.html").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_build_without_conf_fails_cleanly(tmp_path):
    docs = tmp_path / "noconf"
    docs.mkdir()
    (docs / "index.rst").write_text(INDEX, encoding="utf-8")
    app.dependency_overrides[get_store] = lambda: LocalGitStore(docs)
    try:
        client = TestClient(app)
        status = client.post("/api/build").json()
        assert status["state"] == "failed"
        assert any("conf.py" in line for line in status["log_tail"])
    finally:
        app.dependency_overrides.clear()
