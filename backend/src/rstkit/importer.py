"""docx/md -> rst import via pandoc (pypandoc-binary ships the binary).

Conversion strategy:
- pandoc extracts embedded media (docx images) into a TEMP dir first; each
  extracted file is then re-saved through DocumentStore.write_asset, which
  applies the corpus's media/ convention and collision-safe naming, and the
  rst text's URIs are rewritten to the final names. Nothing lands in the
  docs tree except through the same code path the editor's image upload uses.
- Output is normalized to the corpus conventions (CRLF, UTF-8, no BOM) and
  parsed once for a health signal — imports are never rejected for rst
  warnings (converter output is a starting point for cleanup in the editor),
  but the parse error count is surfaced to the UI.

Legacy .doc (pre-2007 Word) is NOT supported by pandoc — the UI says to
save as .docx first.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .parse import parse_rst
from .store import LocalGitStore

_FORMATS = {
    "docx": "docx",
    "md": "markdown",
    "markdown": "markdown",
}


class ImportError_(Exception):
    pass


def supported_extensions() -> set[str]:
    return set(_FORMATS)


def import_to_rst(
    data: bytes, filename: str, store: LocalGitStore, target_rel: str
) -> tuple[str, int]:
    """Convert an uploaded document to rst text, saving any embedded media
    next to `target_rel`. Returns (rst_text, parse_error_count)."""
    import pypandoc

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "doc":
        raise ImportError_(
            "legacy .doc is not supported — open it in Word and save as .docx first"
        )
    fmt = _FORMATS.get(ext)
    if fmt is None:
        raise ImportError_(f"unsupported import type: .{ext or '?'} (use .docx or .md)")

    with tempfile.TemporaryDirectory(prefix="rstkit-import-") as tmp:
        tmp_dir = Path(tmp)
        src = tmp_dir / f"upload.{ext}"
        src.write_bytes(data)
        media_root = tmp_dir / "extracted"
        try:
            rst = pypandoc.convert_file(
                str(src),
                to="rst",
                format=fmt,
                extra_args=[f"--extract-media={media_root.as_posix()}"],
            )
        except Exception as exc:  # pandoc failure: malformed/encrypted file etc.
            raise ImportError_(f"pandoc conversion failed: {exc}") from exc

        # re-home extracted media through the store's collision-safe writer
        # and rewrite the rst's URIs to the final media/ names
        if media_root.is_dir():
            for file in sorted(media_root.rglob("*")):
                if not file.is_file():
                    continue
                new_uri = store.write_asset(target_rel, file.name, file.read_bytes())
                old_uri = file.relative_to(tmp_dir).as_posix()
                rst = rst.replace(f"{media_root.as_posix()}/{file.relative_to(media_root).as_posix()}", new_uri)
                rst = rst.replace(old_uri, new_uri)

    # corpus conventions: CRLF, single trailing newline
    rst = rst.replace("\r\n", "\n").replace("\r", "\n")
    rst = rst.rstrip("\n") + "\n"
    rst = rst.replace("\n", "\r\n")

    doc = parse_rst(rst.encode("utf-8"), target_rel, check_health=True)
    return rst, doc.parse_errors
