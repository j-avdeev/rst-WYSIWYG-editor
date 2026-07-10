from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from rstkit.images import ImageEditError, transform_asset
from rstkit.store import LocalGitStore, PathOutsideRootError

from ..deps import get_store

router = APIRouter()

# Sphinx/docutils recognize these as image formats; reject anything else so
# an accidental non-image paste can't land arbitrary files in the docs tree.
_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.get("/api/asset")
def get_asset(
    doc: str, uri: str, store: LocalGitStore = Depends(get_store)
) -> FileResponse:
    try:
        path = store.resolve_asset(doc, uri)
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="asset path escapes project root")
    if path is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path)


class CropRect(BaseModel):
    x: int
    y: int
    width: int
    height: int


class TransformRequest(BaseModel):
    doc: str
    uri: str
    op: str            # rotate90 | flip_h | flip_v | crop
    crop: CropRect | None = None


@router.post("/api/asset/transform")
def transform(req: TransformRequest, store: LocalGitStore = Depends(get_store)) -> dict:
    try:
        new_uri = transform_asset(
            store,
            req.doc,
            req.uri,
            req.op,
            req.crop.model_dump() if req.crop else None,
        )
    except ImageEditError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="path escapes project root")
    return {"uri": new_uri}


@router.post("/api/asset")
async def upload_asset(
    doc: str = Form(...),
    file: UploadFile = File(...),
    store: LocalGitStore = Depends(get_store),
) -> dict:
    name = file.filename or "image.png"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"unsupported image type: {ext or '(none)'}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="empty upload")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="image too large (max 20MB)")

    try:
        uri = store.write_asset(doc, name, data)
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="path escapes project root")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="referencing document not found")

    return {"uri": uri}
