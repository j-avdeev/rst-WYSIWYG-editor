"""Substitution index: resolve ``|name|`` references for display.

The PRADIS corpus defines its substitution icons (``|Fluid|`` etc.) as plain
``.. |name| image::`` directives inside the *same file* that uses them
(confirmed by corpus survey: 3,119 such definitions, roughly matching icon
usage in csv-table cells) — so a per-file scan is sufficient for Phase 1.
Cross-file definitions (via rst_prolog or a shared include) simply render as
an unresolved chip in the editor, which is the documented safe fallback.

This never affects serialization: substitution references always serialize
as ``|name|`` verbatim regardless of whether resolution succeeded.
"""

from __future__ import annotations

import re

_SUBST_IMAGE_RE = re.compile(
    r"^[ \t]*\.\.[ \t]+\|([^|\n]+)\|[ \t]+image::[ \t]*(\S+)[ \t]*\r?$", re.M
)
_SUBST_REPLACE_RE = re.compile(
    r"^[ \t]*\.\.[ \t]+\|([^|\n]+)\|[ \t]+replace::[ \t]*(.+?)[ \t]*\r?$", re.M
)


def scan_substitutions(text: str) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for m in _SUBST_IMAGE_RE.finditer(text):
        name, uri = m.group(1).strip(), m.group(2).strip()
        index[name] = {"kind": "image", "uri": uri}
    for m in _SUBST_REPLACE_RE.finditer(text):
        name, value = m.group(1).strip(), m.group(2).strip()
        index.setdefault(name, {"kind": "replace", "text": value})
    return index
