from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from rstkit.assemble import SaveBlock, _normalize_eol
from rstkit.pmserialize import SerializeError
from rstkit.preview import render_preview
from rstkit.store import LocalGitStore
from rstkit.verify import VerifyError, serialize_and_verify_block

from ..deps import get_store

router = APIRouter()


class PreviewRequest(BaseModel):
    path: str
    blocks: list[SaveBlock]


class PreviewBlockOut(BaseModel):
    text: str
    dirty: bool
    error: str | None = None


@router.post("/api/preview")
def preview(req: PreviewRequest, store: LocalGitStore = Depends(get_store)) -> dict:
    """Tolerant assembly + render: a block that fails to serialize shows an
    inline error instead of failing the whole preview (unlike save, which
    rejects). Returns per-block text for the source-view pane."""
    out_blocks: list[PreviewBlockOut] = []
    for block in req.blocks:
        if block.op == "raw":
            out_blocks.append(
                PreviewBlockOut(text=_normalize_eol(block.raw or "", "\n"), dirty=False)
            )
            continue
        if block.op == "rawedit":
            text = _normalize_eol(block.raw or "", "\n").rstrip("\n") + "\n"
            out_blocks.append(PreviewBlockOut(text=text, dirty=True))
            continue
        try:
            body = serialize_and_verify_block(block.pm or {})
            out_blocks.append(PreviewBlockOut(text=body + "\n", dirty=True))
        except (SerializeError, VerifyError) as exc:
            out_blocks.append(
                PreviewBlockOut(
                    text=f".. serialize error: {exc}\n", dirty=True, error=str(exc)
                )
            )

    # join with blank-line separation for dirty blocks (mirrors assemble.py)
    pieces: list[str] = []
    for i, b in enumerate(out_blocks):
        text = b.text
        if pieces and not "".join(pieces).endswith("\n\n"):
            pieces.append("\n")
        pieces.append(text)
        if b.dirty and i < len(out_blocks) - 1:
            pieces.append("\n")
    full_text = "".join(pieces)

    try:
        source_abspath = str(store.abspath(req.path))
    except Exception:
        source_abspath = None
    html = render_preview(full_text, req.path, source_abspath)

    return {
        "text": full_text,
        "html": html,
        "blocks": [b.model_dump() for b in out_blocks],
    }
