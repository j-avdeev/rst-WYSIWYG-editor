"""Editor document model (EdDoc): the JSON structure exchanged with the frontend.

Spans are [start, end) indices into the file's line table (lines split with
keepends=True), so ``"".join(lines[start:end])`` is the node's exact original
text including its line endings. Blank-line runs between blocks belong to the
*preceding* block's span, so top-level spans always partition the file.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

# Block-level node types produced in Phase 0. Rich types (csv_table, figure,
# math_block, ...) are introduced per whitelist phase; anything not yet
# understood stays "text" / "directive" and is rendered as an opaque card.
BLOCK_TYPES = (
    "heading",      # attrs: depth, underline, overline (bool)
    "directive",    # attrs: name  (all directives are opaque in Phase 0)
    "comment",      # explicit markup block that is not a directive
    "transition",
    "text",         # paragraph / list / any other body text run
)


def _new_id() -> str:
    return uuid.uuid4().hex


class EdNode(BaseModel):
    id: str = Field(default_factory=_new_id)
    type: str
    span: tuple[int, int]
    raw_source: str
    attrs: dict[str, Any] = Field(default_factory=dict)
    children: list["EdNode"] = Field(default_factory=list)


class EdDoc(BaseModel):
    path: str
    encoding: str          # codec used to decode ("utf-8", "cp1251", ...)
    bom: bool              # UTF-8 BOM present
    eol: str               # "crlf" | "lf" | "mixed" | "none"
    nodes: list[EdNode]
    warnings: list[str] = Field(default_factory=list)
    # docutils parse health: count of system messages at ERROR level or above
    parse_errors: int = 0
