"""App settings. RSTKIT_ROOT points at a Sphinx source directory (the one
containing conf.py) — defaults to the PRADIS docs used for development."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ROOT = r"C:\work\pradis-docs-git\docs\pradis-sphinx-doc"

# Enrichment (paragraph/inline rendering) is skipped past this size — the
# per-fragment docutils re-parse cost scales with node count, and the
# corpus's 463KB outlier takes ~4s to enrich in full. Phase 6 replaces this
# with proper outline/lazy-section rendering; for now the file still opens,
# just as plain preformatted blocks instead of rich paragraphs.
ENRICH_SIZE_LIMIT_BYTES = 150_000


def get_root() -> Path:
    root = os.environ.get("RSTKIT_ROOT", DEFAULT_ROOT)
    return Path(root).resolve()
