"""Identity round-trip over the committed fixture corpus (real PRADIS pages).

This is the CI stand-in for the full-corpus run
(`uv run rstkit roundtrip C:\\work\\pradis-docs-git\\docs`), which is executed
locally. Both must stay at 100% byte-identical.
"""

import time
from pathlib import Path

import pytest

from rstkit.parse import parse_rst
from rstkit.serialize import serialize

CORPUS = Path(__file__).parent / "fixtures" / "corpus"
FILES = sorted(CORPUS.rglob("*.rst"))


def test_fixture_corpus_present():
    assert len(FILES) >= 40, "fixture corpus went missing or was trimmed"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(CORPUS)))
def test_fixture_identity(path):
    data = path.read_bytes()
    doc = parse_rst(data, str(path), check_health=True)
    assert serialize(doc) == data
    assert doc.parse_errors == 0, f"docutils errors in {path.name}"


def test_huge_file_parse_speed():
    """errors.rst (463 KB) must scan fast; docutils health is the slow part
    and is skipped here — the editor open path can defer it too."""
    path = max(FILES, key=lambda p: p.stat().st_size)
    data = path.read_bytes()
    t0 = time.monotonic()
    doc = parse_rst(data, str(path), check_health=False)
    elapsed = time.monotonic() - t0
    assert serialize(doc) == data
    assert elapsed < 2.0, f"scan of {path.name} took {elapsed:.2f}s"
