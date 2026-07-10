"""Image transforms for the editor's image card: rotate 90° CW, flip, crop.

Every transform writes a NEW file through the store's collision-safe
write_asset and returns its URI — the original is never overwritten, because
corpus images (substitution icons especially) can be referenced from many
documents. The caller swaps the directive's URI, so the rst diff stays one
line and git keeps the old image until someone deliberately removes it.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from .store import LocalGitStore

OPS = {"rotate90", "flip_h", "flip_v", "crop"}

# formats Pillow can round-trip well enough for docs images
_SAVE_FORMAT = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".gif": "GIF",
    ".bmp": "BMP",
    ".webp": "WEBP",
}


class ImageEditError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def transform_asset(
    store: LocalGitStore,
    doc_rel: str,
    uri: str,
    op: str,
    crop: dict[str, Any] | None = None,
) -> str:
    from PIL import Image

    if op not in OPS:
        raise ImageEditError(f"unknown operation {op!r}")

    source = store.resolve_asset(doc_rel, uri)
    if source is None:
        raise ImageEditError("image not found", status=404)

    ext = source.suffix.lower()
    fmt = _SAVE_FORMAT.get(ext)
    if fmt is None:
        raise ImageEditError(
            f"cannot edit {ext or 'extensionless'} images (vector or unsupported format)",
            status=415,
        )

    try:
        img = Image.open(source)
        img.load()
    except Exception as exc:
        raise ImageEditError(f"cannot read image: {exc}") from exc

    if op == "rotate90":
        # PIL's ROTATE_90 is counter-clockwise; users asked for clockwise
        out = img.transpose(Image.Transpose.ROTATE_270)
    elif op == "flip_h":
        out = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif op == "flip_v":
        out = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    else:  # crop
        if not crop:
            raise ImageEditError("crop rectangle is required")
        try:
            x, y = int(crop["x"]), int(crop["y"])
            w, h = int(crop["width"]), int(crop["height"])
        except (KeyError, TypeError, ValueError):
            raise ImageEditError("crop needs integer x, y, width, height") from None
        if w < 1 or h < 1:
            raise ImageEditError("crop rectangle is empty")
        if x < 0 or y < 0 or x + w > img.width or y + h > img.height:
            raise ImageEditError(
                f"crop rectangle {x},{y} {w}x{h} exceeds image bounds "
                f"{img.width}x{img.height}"
            )
        out = img.crop((x, y, x + w, y + h))

    buf = io.BytesIO()
    save_kwargs: dict[str, Any] = {"quality": 95} if fmt == "JPEG" else {}
    if fmt == "JPEG" and out.mode not in ("RGB", "L"):
        out = out.convert("RGB")
    out.save(buf, format=fmt, **save_kwargs)

    stem = Path(source.name).stem
    return store.write_asset(doc_rel, f"{stem}_edited{ext}", buf.getvalue())
