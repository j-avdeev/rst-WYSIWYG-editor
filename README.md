# rst WYSIWYG Editor

Semi-WYSIWYG editor for Sphinx `.rst` projects (built for the PRADIS Manual,
`C:\work\pradis-docs-git\docs`). Local-first web app: Python/FastAPI backend +
ProseMirror frontend. Core guarantee: **files round-trip byte-identical** —
only blocks you actually edit are re-serialized, so git diffs stay minimal.

Development plan: see `.claude/plans/` (approved 2026-07). Current status:
**Phase 2 complete** — the editing core. Rich blocks (headings, paragraphs,
lists, literal blocks) are editable in ProseMirror; opaque cards edit as raw
source in a modal. Saving re-emits untouched blocks byte-for-byte and routes
every edited block through serialize → re-parse → canonical-compare
(verify-reparse); a failed verification rejects the save instead of writing.
Live server-rendered preview + source view with dirty-block highlighting.

## Layout

- `backend/src/rstkit/` — rst round-trip engine (no web dependencies)
  - `parse.py` — span-partition scanner + docutils parse-health
  - `serialize.py` — identity/dirty-node serializer
  - `inline.py` — best-effort rendering enrichment (isolate-parses each
    block's own raw_source into a paragraph/list/inline-mark tree; never
    affects round-trip fidelity)
  - `subst.py` — per-file `|name|` substitution index
  - `store.py` — `DocumentStore` protocol + `LocalGitStore`
  - `cli.py` — `rstkit roundtrip` corpus harness (the permanent quality gate)
- `backend/src/app/` — FastAPI app: `/api/project`, `/api/files`,
  `/api/doc/{path}`, `/api/asset`
- `frontend/` — Vite + React + TypeScript + ProseMirror (read-only in Phase 1;
  the same schema carries into Phase 2's editing core)

## Quality gate

```powershell
cd backend
uv run pytest                                        # unit + fixture corpus + API tests
uv run rstkit roundtrip C:\work\pradis-docs-git\docs # identity: 100% byte-identical
uv run rstkit strict C:\work\pradis-docs-git\docs    # force-reserialize editable blocks
```

Pass criteria: identity mode 100% byte-identical over all 2,093 corpus files;
strict mode ≥95% (currently 100.00% over 10,884 editable blocks). Re-run after
every change that touches `rstkit/`.

## Running it

```powershell
powershell -File scripts\dev.ps1
```

Backend on :8010, frontend (Vite) on :5173 proxying `/api` to the backend.
Override the docs root with `-Root <sphinx-source-dir>`.

## Requirements

- Python ≥3.11 via [uv](https://docs.astral.sh/uv/) (docutils pinned to 0.21.2
  to match the PRADIS Sphinx 8.2.3 build environment)
- Node 20+ / pnpm
