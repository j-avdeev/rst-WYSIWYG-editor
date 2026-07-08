from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rstkit.assemble import AssembleIssue, SaveBlock, assemble, check_health_regression
from rstkit.inline import enrich_nodes
from rstkit.parse import SourceText, parse_rst
from rstkit.store import LocalGitStore, PathOutsideRootError
from rstkit.subst import scan_substitutions

from ..config import ENRICH_SIZE_LIMIT_BYTES
from ..deps import get_store

router = APIRouter()

_BOM = b"\xef\xbb\xbf"


def _doc_payload(data: bytes, rel_path: str, mtime_ns: int) -> dict:
    doc = parse_rst(data, rel_path, check_health=True)
    enriched = len(data) <= ENRICH_SIZE_LIMIT_BYTES
    if enriched:
        enrich_nodes(doc.nodes)
    text = data.decode(doc.encoding, "replace")
    return {
        "doc": doc.model_dump(),
        "enriched": enriched,
        "size_bytes": len(data),
        "substitutions": scan_substitutions(text),
        "mtime_ns": mtime_ns,
    }


def _read(store: LocalGitStore, rel_path: str) -> bytes:
    try:
        return store.read_bytes(rel_path)
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="path escapes project root")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")


@router.get("/api/doc/{rel_path:path}")
def get_doc(rel_path: str, store: LocalGitStore = Depends(get_store)) -> dict:
    data = _read(store, rel_path)
    return _doc_payload(data, rel_path, store.mtime_ns(rel_path))


class SaveRequest(BaseModel):
    base_mtime_ns: int
    blocks: list[SaveBlock]


@router.put("/api/doc/{rel_path:path}")
def save_doc(
    rel_path: str, req: SaveRequest, store: LocalGitStore = Depends(get_store)
) -> dict:
    old_data = _read(store, rel_path)

    current_mtime = store.mtime_ns(rel_path)
    if current_mtime != req.base_mtime_ns:
        raise HTTPException(
            status_code=409,
            detail="file changed on disk since it was opened; reload before saving",
        )

    src = SourceText(old_data)
    try:
        new_text = assemble(req.blocks, src.eol)
        check_health_regression(src.text, new_text, rel_path)
    except AssembleIssue as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    new_data = new_text.encode(src.encoding)
    if src.bom:
        new_data = _BOM + new_data

    store.write_bytes(rel_path, new_data)
    return _doc_payload(new_data, rel_path, store.mtime_ns(rel_path))
