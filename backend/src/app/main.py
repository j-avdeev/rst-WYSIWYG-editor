from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import assets, docs, files, git, pages, preview, project

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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
