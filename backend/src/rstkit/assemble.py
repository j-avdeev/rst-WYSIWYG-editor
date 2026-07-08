"""Assemble a saved document from an ordered block list.

Block ops (wire format of PUT /api/doc and POST /api/preview):

- ``raw``     — clean block: the original raw_source, emitted verbatim
                (byte-exact by construction; raw-raw junctions are never
                altered, so an unedited file reassembles identically).
- ``rawedit`` — opaque card edited as raw text in the modal: used as-is
                after EOL normalization to the file's style.
- ``node``    — dirty rich block as PM JSON: serialized + verify-reparsed
                (rstkit.verify); joined with the file's EOL and isolated by
                blank lines on both sides.

Whole-file gates (save only): the assembled text must still scan into a
valid partition, and its docutils error count must not exceed the original
file's. Any gate failure raises — the file on disk is never touched.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from .parse import parse_rst
from .pmserialize import SerializeError
from .verify import VerifyError, serialize_and_verify_block

_EOL = {"crlf": "\r\n", "lf": "\n", "mixed": "\r\n", "none": "\r\n"}


class SaveBlock(BaseModel):
    op: Literal["raw", "rawedit", "node"]
    raw: str | None = None
    pm: dict[str, Any] | None = None


class AssembleIssue(Exception):
    def __init__(self, index: int, message: str):
        super().__init__(f"block {index}: {message}")
        self.index = index


def _normalize_eol(text: str, eol: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", eol)


def _ends_with_blank_line(text: str) -> bool:
    if not text:
        return True  # start of file needs no separator
    tail = text[-8:].replace("\r\n", "\n").replace("\r", "\n")
    return tail.endswith("\n\n")


def assemble(blocks: list[SaveBlock], eol_style: str) -> str:
    """Build the new full text. Raises AssembleIssue (wrapping Serialize/
    VerifyError) on the first failing block."""
    eol = _EOL.get(eol_style, "\r\n")
    out: list[str] = []

    def acc() -> str:
        return "".join(out)

    for i, block in enumerate(blocks):
        if block.op == "raw":
            if block.raw is None:
                raise AssembleIssue(i, "raw block without text")
            out.append(block.raw)
            continue

        if block.op == "rawedit":
            if block.raw is None:
                raise AssembleIssue(i, "rawedit block without text")
            text = _normalize_eol(block.raw, eol).rstrip() + eol
        else:  # node
            if block.pm is None:
                raise AssembleIssue(i, "node block without pm json")
            try:
                body = serialize_and_verify_block(block.pm)
            except (SerializeError, VerifyError) as exc:
                raise AssembleIssue(i, str(exc)) from exc
            text = _normalize_eol(body, eol) + eol

        if not _ends_with_blank_line(acc()):
            out.append(eol)
        out.append(text)
        is_last = i == len(blocks) - 1
        if not is_last:
            out.append(eol)  # blank line isolating the edited block

    return acc()


def check_health_regression(old_text: str, new_text: str, path: str) -> None:
    """The saved file must not be more broken than the original."""
    old = parse_rst(old_text.encode("utf-8"), path).parse_errors
    new = parse_rst(new_text.encode("utf-8"), path).parse_errors
    if new > old:
        raise AssembleIssue(
            -1, f"save would introduce rst errors ({old} -> {new}); rejected"
        )
