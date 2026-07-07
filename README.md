# rst WYSIWYG Editor

Semi-WYSIWYG editor for Sphinx `.rst` projects (built for the PRADIS Manual,
`C:\work\pradis-docs-git\docs`). Local-first web app: Python/FastAPI backend +
ProseMirror frontend. Core guarantee: **files round-trip byte-identical** —
only blocks you actually edit are re-serialized, so git diffs stay minimal.

Development plan: see `.claude/plans/` (approved 2026-07). Current status:
**Phase 0 complete** — round-trip engine + corpus harness.

## Layout

- `backend/src/rstkit/` — rst round-trip engine (no web dependencies)
  - `parse.py` — span-partition scanner + docutils parse-health
  - `serialize.py` — identity/dirty-node serializer
  - `cli.py` — `rstkit roundtrip` corpus harness (the permanent quality gate)
- `backend/src/app/` — FastAPI app (Phase 1+)
- `frontend/` — Vite + React + ProseMirror (Phase 1+)

## Quality gate

```powershell
cd backend
uv run pytest                                        # unit + fixture corpus
uv run rstkit roundtrip C:\work\pradis-docs-git\docs # full corpus, must PASS
```

Pass criterion: 100% byte-identical over all 2,093 corpus files.

## Requirements

- Python ≥3.11 via [uv](https://docs.astral.sh/uv/) (docutils pinned to 0.21.2
  to match the PRADIS Sphinx 8.2.3 build environment)
- Node 20+ / pnpm (from Phase 1)
