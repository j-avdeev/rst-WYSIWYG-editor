"""API tests running against the committed fixture corpus (not the live
C:\\work\\pradis-docs-git checkout, so these run anywhere including CI)."""

import os
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "corpus"

os.environ["RSTKIT_ROOT"] = str(FIXTURES)

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app

get_store.cache_clear()
client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_project():
    r = client.get("/api/project")
    assert r.status_code == 200
    assert r.json()["root"] == str(FIXTURES.resolve())


def test_file_tree_contains_known_file():
    r = client.get("/api/files")
    assert r.status_code == 200
    tree = r.json()

    def find(entry, target):
        if not entry["is_dir"] and entry["path"] == target:
            return True
        return any(find(c, target) for c in entry.get("children", []))

    assert find(tree, "pradis-sphinx-doc/index.rst")


def test_get_doc_index():
    r = client.get("/api/doc/pradis-sphinx-doc/index.rst")
    assert r.status_code == 200
    body = r.json()
    assert body["enriched"] is True
    assert body["doc"]["path"] == "pradis-sphinx-doc/index.rst"
    assert any(n["type"] == "heading" for n in body["doc"]["nodes"])


def test_get_doc_missing_returns_404():
    r = client.get("/api/doc/pradis-sphinx-doc/does-not-exist.rst")
    assert r.status_code == 404


def test_get_doc_path_traversal_rejected():
    r = client.get("/api/doc/..%2F..%2Fsecrets.rst")
    assert r.status_code in (400, 404)


def test_get_doc_huge_file_skips_enrichment():
    r = client.get("/api/doc/pradis-sphinx-doc/doc_sprav/errors/errors.rst")
    assert r.status_code == 200
    body = r.json()
    assert body["enriched"] is False
    assert all(n["view"] is None for n in body["doc"]["nodes"])


def test_substitutions_resolved_for_a_file_that_defines_icons():
    # find a fixture file that defines at least one |name| image substitution
    for path in FIXTURES.rglob("*.rst"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if ".. |" in text and "image::" in text:
            rel = path.relative_to(FIXTURES).as_posix()
            r = client.get(f"/api/doc/{rel}")
            assert r.status_code == 200
            assert len(r.json()["substitutions"]) >= 1
            return
    pytest.skip("no fixture defines a substitution image")


def test_asset_resolution_relative_to_doc():
    # find a fixture referencing a local image and confirm /api/asset serves it
    import re

    for path in FIXTURES.rglob("*.rst"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"\.\.\s+(?:figure|image)::\s*(\S+\.(?:png|jpg|jpeg|gif|svg))", text)
        if not m:
            continue
        uri = m.group(1)
        doc_rel = path.relative_to(FIXTURES).as_posix()
        candidate = (path.parent / uri) if not uri.startswith("/") else (FIXTURES / uri.lstrip("/"))
        if not candidate.exists():
            continue
        r = client.get("/api/asset", params={"doc": doc_rel, "uri": uri})
        assert r.status_code == 200
        return
    pytest.skip("no fixture references a locally-present image asset")
