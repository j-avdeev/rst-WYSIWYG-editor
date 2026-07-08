"""Image upload endpoint tests, against a throwaway copy of a real fixture
(never the fixture corpus itself, which every other test reads as read-only)."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app
from rstkit.store import LocalGitStore

FIXTURES = Path(__file__).parent / "fixtures" / "corpus"
REL = "pradis-sphinx-doc/index.rst"

_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


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


def test_upload_saves_under_media_and_returns_relative_uri(workspace):
    root, client = workspace
    r = client.post(
        "/api/asset",
        data={"doc": REL},
        files={"file": ("screenshot.png", _PNG_1PX, "image/png")},
    )
    assert r.status_code == 200, r.text
    uri = r.json()["uri"]
    assert uri == "media/screenshot.png"
    saved = root / "pradis-sphinx-doc" / "media" / "screenshot.png"
    assert saved.read_bytes() == _PNG_1PX


def test_upload_collision_gets_suffixed(workspace):
    root, client = workspace
    for _ in range(2):
        r = client.post(
            "/api/asset",
            data={"doc": REL},
            files={"file": ("dup.png", _PNG_1PX, "image/png")},
        )
        assert r.status_code == 200
    uris = set()
    for _ in range(3):
        r = client.post(
            "/api/asset",
            data={"doc": REL},
            files={"file": ("dup.png", _PNG_1PX, "image/png")},
        )
        uris.add(r.json()["uri"])
    assert len(uris) == 3  # each upload gets a distinct filename


def test_upload_sanitizes_filename(workspace):
    root, client = workspace
    r = client.post(
        "/api/asset",
        data={"doc": REL},
        files={"file": ("weird name!@#.png", _PNG_1PX, "image/png")},
    )
    assert r.status_code == 200
    uri = r.json()["uri"]
    assert uri.startswith("media/weird_name")
    assert (root / "pradis-sphinx-doc" / uri).exists()


def test_upload_rejects_non_image_extension(workspace):
    _, client = workspace
    r = client.post(
        "/api/asset",
        data={"doc": REL},
        files={"file": ("script.exe", b"MZ...", "application/octet-stream")},
    )
    assert r.status_code == 415


def test_upload_rejects_empty_file(workspace):
    _, client = workspace
    r = client.post(
        "/api/asset",
        data={"doc": REL},
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert r.status_code == 422


def test_uploaded_image_is_immediately_fetchable(workspace):
    _, client = workspace
    r = client.post(
        "/api/asset",
        data={"doc": REL},
        files={"file": ("pic.png", _PNG_1PX, "image/png")},
    )
    uri = r.json()["uri"]
    r2 = client.get("/api/asset", params={"doc": REL, "uri": uri})
    assert r2.status_code == 200
    assert r2.content == _PNG_1PX


def test_upload_path_traversal_in_doc_rejected(workspace):
    _, client = workspace
    r = client.post(
        "/api/asset",
        data={"doc": "../../../../outside.rst"},
        files={"file": ("pic.png", _PNG_1PX, "image/png")},
    )
    assert r.status_code in (400, 404)
