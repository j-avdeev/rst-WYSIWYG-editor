from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .routers import assets, build, docs, files, git, pages, preview, project, toc

app = FastAPI(title="rst WYSIWYG editor backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project.router)
app.include_router(files.router)
app.include_router(docs.router)
app.include_router(assets.router)
app.include_router(preview.router)
app.include_router(git.router)
app.include_router(pages.router)
app.include_router(build.router)
app.include_router(toc.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Production mode: serve the built frontend (frontend/dist) directly, so end
# users need no Node/Vite — just the backend. The catch-all is registered
# LAST: every /api/* and /built/* route above matches first, and anything
# else gets a static file or the SPA's index.html.

def _frontend_dist() -> Path | None:
    import os

    env = os.environ.get("RSTKIT_FRONTEND_DIST")
    candidates = [Path(env)] if env else []
    candidates.append(Path(__file__).resolve().parents[3] / "frontend" / "dist")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


@app.get("/{spa_path:path}", include_in_schema=False)
def spa(spa_path: str) -> FileResponse:
    dist = _frontend_dist()
    if dist is None:
        raise HTTPException(
            status_code=404,
            detail="frontend not built — run `pnpm build` in frontend/ or use the Vite dev server",
        )
    candidate = (dist / spa_path.lstrip("/\\")).resolve() if spa_path else dist / "index.html"
    try:
        candidate.relative_to(dist)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad path")
    if not candidate.is_file():
        candidate = dist / "index.html"  # SPA fallback
    media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return FileResponse(candidate, media_type=media_type)
