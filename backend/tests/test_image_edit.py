"""Image transform ops: rotate 90° CW, flips, crop — with a marker pixel to
prove directions, never touching the original file."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.deps import get_store
from app.main import app
from rstkit.store import LocalGitStore

FIXTURES = Path(__file__).parent / "fixtures" / "corpus"
REL = "pradis-sphinx-doc/index.rst"


@pytest.fixture()
def workspace(tmp_path):
    root = tmp_path / "docs"
    dst = root / REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / REL, dst)

    # 4x2 white image with a red marker at top-left (0,0)
    img = Image.new("RGB", (4, 2), "white")
    img.putpixel((0, 0), (255, 0, 0))
    media = dst.parent / "media"
    media.mkdir()
    img.save(media / "pic.png")

    app.dependency_overrides[get_store] = lambda: LocalGitStore(root)
    client = TestClient(app)
    yield root, client
    app.dependency_overrides.clear()


def _transform(client, op, crop=None):
    return client.post(
        "/api/asset/transform",
        json={"doc": REL, "uri": "media/pic.png", "op": op, "crop": crop},
    )


def _open(root, uri):
    return Image.open(root / "pradis-sphinx-doc" / uri)


def test_rotate90_clockwise(workspace):
    root, client = workspace
    r = _transform(client, "rotate90")
    assert r.status_code == 200, r.text
    out = _open(root, r.json()["uri"])
    assert out.size == (2, 4)  # dimensions swap
    # top-left marker moves to top-right under clockwise rotation
    assert out.getpixel((1, 0)) == (255, 0, 0)


def test_flip_horizontal(workspace):
    root, client = workspace
    r = _transform(client, "flip_h")
    out = _open(root, r.json()["uri"])
    assert out.size == (4, 2)
    assert out.getpixel((3, 0)) == (255, 0, 0)  # marker mirrored to the right


def test_flip_vertical(workspace):
    root, client = workspace
    r = _transform(client, "flip_v")
    out = _open(root, r.json()["uri"])
    assert out.getpixel((0, 1)) == (255, 0, 0)  # marker mirrored to the bottom


def test_crop_exact_region(workspace):
    root, client = workspace
    r = _transform(client, "crop", {"x": 0, "y": 0, "width": 2, "height": 1})
    out = _open(root, r.json()["uri"])
    assert out.size == (2, 1)
    assert out.getpixel((0, 0)) == (255, 0, 0)


def test_crop_out_of_bounds_rejected(workspace):
    _, client = workspace
    r = _transform(client, "crop", {"x": 2, "y": 0, "width": 10, "height": 1})
    assert r.status_code == 422
    assert "bounds" in r.json()["detail"]


def test_original_file_untouched_and_new_uri_distinct(workspace):
    root, client = workspace
    original = (root / "pradis-sphinx-doc" / "media" / "pic.png").read_bytes()
    r = _transform(client, "rotate90")
    uri = r.json()["uri"]
    assert uri != "media/pic.png"
    assert (root / "pradis-sphinx-doc" / "media" / "pic.png").read_bytes() == original
    # new file resolvable through the normal asset endpoint
    assert client.get("/api/asset", params={"doc": REL, "uri": uri}).status_code == 200


def test_svg_rejected(workspace):
    root, client = workspace
    (root / "pradis-sphinx-doc" / "media" / "v.svg").write_text("<svg/>", encoding="utf-8")
    r = client.post(
        "/api/asset/transform",
        json={"doc": REL, "uri": "media/v.svg", "op": "rotate90"},
    )
    assert r.status_code == 415


def test_missing_image_404(workspace):
    _, client = workspace
    r = client.post(
        "/api/asset/transform",
        json={"doc": REL, "uri": "media/nope.png", "op": "flip_h"},
    )
    assert r.status_code == 404
