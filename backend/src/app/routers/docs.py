from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from rstkit.inline import enrich_nodes
from rstkit.parse import parse_rst
from rstkit.store import LocalGitStore, PathOutsideRootError
from rstkit.subst import scan_substitutions

from ..config import ENRICH_SIZE_LIMIT_BYTES
from ..deps import get_store

router = APIRouter()


@router.get("/api/doc/{rel_path:path}")
def get_doc(rel_path: str, store: LocalGitStore = Depends(get_store)) -> dict:
    try:
        data = store.read_bytes(rel_path)
    except PathOutsideRootError:
        raise HTTPException(status_code=400, detail="path escapes project root")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")

    doc = parse_rst(data, rel_path, check_health=True)

    enriched = len(data) <= ENRICH_SIZE_LIMIT_BYTES
    if enriched:
        enrich_nodes(doc.nodes)

    text = data.decode(doc.encoding, "replace")
    substitutions = scan_substitutions(text)

    return {
        "doc": doc.model_dump(),
        "enriched": enriched,
        "size_bytes": len(data),
        "substitutions": substitutions,
    }
