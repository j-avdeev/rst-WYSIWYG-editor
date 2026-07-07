"""Serialize an EdDoc back to rst bytes.

Identity mode (Phase 0): concatenate every node's raw_source — byte-identical
by construction when the span partition holds. Dirty-node serialization
(re-emitting only edited nodes from structure) arrives in Phase 2 and slots
into the same concatenation loop.
"""

from __future__ import annotations

from .model import EdDoc

_BOM = b"\xef\xbb\xbf"


def serialize(doc: EdDoc) -> bytes:
    text = "".join(node.raw_source for node in doc.nodes)
    data = text.encode(doc.encoding)
    if doc.bom:
        data = _BOM + data
    return data
