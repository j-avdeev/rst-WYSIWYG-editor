"""Production static serving: the backend serves the built frontend so end
users need no Node/Vite. /api and /built routes always win; anything else is
a dist file or the SPA's index.html fallback."""

import pytest
from fastapi.testclient import TestClient

from app.main import app, _frontend_dist

client = TestClient(app)


@pytest.fixture()
def dist(tmp_path, monkeypatch):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>rst editor</title>", encoding="utf-8")
    (d / "assets" / "x.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("RSTKIT_FRONTEND_DIST", str(d))
    yield d


def test_root_serves_index(dist):
    r = client.get("/")
    assert r.status_code == 200
    assert "rst editor" in r.text


def test_asset_file_served_with_mime(dist):
    r = client.get("/assets/x.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_spa_route_falls_back_to_index(dist):
    r = client.get("/some/spa/route")
    assert r.status_code == 200
    assert "rst editor" in r.text


def test_api_routes_still_win(dist):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_missing_dist_gives_hint(monkeypatch, tmp_path):
    monkeypatch.setenv("RSTKIT_FRONTEND_DIST", str(tmp_path / "nowhere"))
    if _frontend_dist() is not None:
        pytest.skip("repo has a real frontend/dist build; fallback hint not reachable")
    r = client.get("/")
    assert r.status_code == 404
    assert "frontend not built" in r.json()["detail"]
