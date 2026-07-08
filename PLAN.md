# Semi-WYSIWYG .rst Editor for Sphinx Projects — Development Plan

> Mirrored into the repo from the approved plan (originally
> `C:\Users\j-avd\.claude\plans\ok-if-i-will-stateless-kite.md`, approved
> 2026-07-08) so it travels with the code regardless of which tool/agent is
> driving development. Keep this file's **Status** section current — it is
> the source of truth for "what's done and what's next."

## Status (update this as phases land)

| Phase | State | Commit(s) | Notes |
|---|---|---|---|
| 0 — Round-trip spike + harness | ✅ done | `947cb30` | Identity mode 100% byte-identical on all 2,093 corpus files |
| 1 — Read-only browser | ✅ done | `2b042a2`, `c9baa36` | FastAPI + file tree + read-only ProseMirror render |
| 2 — Editing core | ✅ done | `29be4e3` | Dirty-node serialize + verify-reparse; `rstkit strict` 100.00% (10,884/10,884 blocks). AC verified on real corpus: one-line edit → exactly one git hunk |
| 3 — csv-table editing | mostly done | `7e3ed3f` | Inline csv-table parser/rendering, dirty-cell serializer with clean-cell raw preservation, row/column toolbar. Full strict 100.00% (13,764/13,764 blocks; 2,879/2,946 csv_table enrich to editable — rest fall back to opaque cards for ragged rows/multiline cells/unsupported options). Remaining: options popover + fuzz/property coverage |
| 4 — figure/image + math | mostly done (out of order) | `7e3ed3f` | Pulled forward ahead of the original plan order per user priority: image insert (paste/drop/toolbar/upload endpoint, media/ convention, collision-safe naming, thumbnail preview, "Replace image..."), inline+block LaTeX math editor (KaTeX live preview, curated symbol toolbar). Not yet done: figure caption as rich editable text (still raw-text-in-modal) and options popover |
| 5 — Git UI + file management | not started | | |
| 6 — Huge files | not started | | errors.rst = 463 KB, the size outlier |
| 7 — Whitelist round-out | not started | | |
| 8 — Import + niceties | not started | | image upload already covers the main paste-screenshot use case originally scoped here; pypandoc docx/md import still open |

**Before touching anything in `backend/src/rstkit/`, run the two quality gates and keep them green:**
```powershell
cd backend
uv run pytest                                          # unit + fixture corpus + API tests
uv run rstkit roundtrip C:\work\pradis-docs-git\docs   # identity: must stay 100% byte-identical
uv run rstkit strict C:\work\pradis-docs-git\docs      # verify-reparse: must stay >=95% (currently 100.00%)
```
Any change that drops either gate below its threshold is a regression, full stop — the whole architecture's promise ("only edited blocks are re-serialized, unedited content round-trips byte-exact") lives or dies by these two commands passing.

**Design principles established the hard way (see commit messages for the bugs that taught these):**
- **Poison, don't drop.** If any part of a block can't be represented in the editor's view model, the *whole* block falls back to an opaque raw-source card. Never silently omit content — that's how edits become lossy. (`rstkit/inline.py`)
- **Verify every dirty block before writing.** Serialize → re-parse → compare in canonical form against editor intent. Mismatch rejects the save (422) rather than writing a corrupted file. (`rstkit/verify.py`)
- **Clean blocks are never re-serialized.** They re-emit their original `raw_source` byte-for-byte. Only touched blocks go through the serializer.
- docutils gotchas already handled, don't rediscover them: NUL bytes mark backslash-escapes in `Text` nodes; escaped whitespace has vanishing semantics (`word\ **bold**` → `wordbold`); Windows PowerShell 5.1 without a UTF-8 BOM misreads non-ASCII in `.ps1` files (see `scripts/dev.ps1`).

---

## Context

Goal: a semi-WYSIWYG editor for Sphinx .rst projects (target: `C:\work\pradis-docs-git\docs`, the PRADIS Manual) so that authors — including non-IT colleagues — can edit docs visually, insert formulas/tables/images/links, and later import .docx/.md. The hard problem is not the UI but the **round-trip**: parsing .rst into an editable structure and writing it back without destroying formatting. This repo started empty; everything is built from scratch.

**Locked decisions (user-confirmed):**
- **Local-first web app**: Python (FastAPI) backend + browser UI running on the user's machine, operating directly on a local git checkout. A clean `DocumentStore` abstraction keeps the door open for a later shared-server deployment with GitLab OAuth (out of scope now).
- **Storage format stays .rst** — no MyST migration. We build a custom round-trip serializer; round-trip fidelity is the project's core quality metric.
- **Built iteratively**, so phases are days-to-weeks sized, each ending usable on the real corpus.

**Ground truth — survey of the actual corpus (defines the whitelist):**
- 2,093 .rst files, 98.8% reference pages in `doc_sprav/`; 1,601 files contain Cyrillic (Russian project) — full Unicode/EOL fidelity is mandatory.
- Construct frequency: **csv-table 2,947 (dominant — cells contain backtick links + `|substitution|` image icons)**, figure 1,932, list-table 421, include 414, parsed-literal 381, math directive 262 (+242 inline `:math:` in ~17 files), rst-class 68, toctree 57, code-block 46 (console/fortran/none/python/text), image 28, grid tables 2, admonitions ~1 file.
- Essentially zero: `:ref:`, `:download:`, footnotes, `.. raw::`, custom directives in markup. `:doc:` only in index.rst.
- Substitutions (e.g. `|Fluid|`) are defined as literal `.. |name| image::` directives, mostly local to the file that uses them (3,119 such definitions corpus-wide) — resolved for display, serialized untouched.
- Sphinx: extensions `sphinx.ext.todo`, `intersphinx`, `sphinx_rtd_theme`, `sphinxcontrib.jquery`, custom `_ext/collapsible_menu` (HTML-only). `master_doc='index'`, language `ru`. Build env: Sphinx 8.2.3 / docutils 0.21.2 (pinned in `backend/pyproject.toml`).
- Size tail: `errors.rst` = **463 KB single file**, `preprocessor.rst` 84 KB, `methods_of_pradis.rst` 61 KB (math-heavy) — editor must not choke.

## Architecture

### Stack
| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python 3.11+, **uv**, FastAPI, pydantic v2 | docutils/Sphinx/pypandoc live in Python; uv avoids venv friction in PowerShell |
| rst engine | **docutils pinned to 0.21.2** (matches PRADIS's Sphinx 8.2.3) | doctree shapes drift across versions; harness must match production |
| Frontend | Vite + React 18 + TypeScript + pnpm | React only for chrome; editor pane is raw ProseMirror |
| Editor | **ProseMirror direct (not TipTap)** + prosemirror-tables + prosemirror-schema-list | Schema is ~100% custom and serialization bypasses HTML — TipTap's value doesn't apply |
| Source/raw editing | Native textarea modal for opaque cards (CodeMirror upgrade optional later) | source-view pane + opaque-card raw editor |
| Math | KaTeX (Phase 4); Phase 1-2 render raw LaTeX as a styled chip | best-effort in-editor render; Sphinx/docutils MathML is the truth in preview |
| Git | subprocess (`git status --porcelain=v2` etc.) behind `DocumentStore` | avoids pygit2 Windows build pain; seam for later GitLab API |
| Import | pypandoc (Phase 8) | docx/md → rst |
| Tests | pytest (load-bearing), Vitest/tsc (frontend) | |

### Repo layout (monorepo)
```
backend/
  pyproject.toml
  src/rstkit/        # core lib, ZERO web deps
    model.py         # editor-JSON document model (EdDoc / EdNode)
    parse.py         # docutils parse + source-span mapping  <- fidelity linchpin
    serialize.py      # identity serializer (span concatenation)
    inline.py         # rendering enrichment: isolated per-block parse -> view tree
    pmserialize.py    # PM JSON -> rst text (dirty-block serializer)
    verify.py         # canonical-form compare: PM intent vs re-parsed rst
    assemble.py        # block list -> full file text + whole-file gates
    pmbridge.py        # view tree -> PM JSON (mirrors frontend convert.ts, for corpus-wide testing)
    subst.py           # per-file |name| substitution index
    store.py            # DocumentStore protocol + LocalGitStore
    preview.py          # docutils html5 render for the preview pane
    cli.py               # `rstkit roundtrip` / `rstkit strict` corpus harnesses
  src/app/             # FastAPI routers, preview, asset serving
  tests/                # fixtures = real corpus snippets (incl. Cyrillic, CRLF)
frontend/
  src/editor/          # PM schema.ts, convert.ts (EdDoc->PM), dirty.ts, Editor.tsx
  src/panels/          # file tree, RightPanel (preview/source)
  src/api/             # typed client
scripts/dev.ps1        # uvicorn --reload + vite dev (proxy /api -> backend)
.github/workflows/ci.yml
```

### Core data flow & fidelity strategy — span-anchored dirty-node serialization
`rst bytes -> docutils parse -> span-annotated EdDoc JSON -> ProseMirror doc -> edits -> dirty-node serializer -> rst bytes`

- **No custom CST parser, no full re-serialization.** A line-scanner (`parse.py::scan_blocks`) assigns every source line to exactly one top-level block, independent of docutils' notoriously unreliable line numbers. **Invariant: top-level spans partition the file — no gaps, no overlaps** (checked by `verify_partition` on every parse).
- Every node carries `raw_source` (exact slice of the original text) + best-effort `view` (rendering enrichment, built by isolate-parsing that node's own `raw_source` through docutils — see `inline.py`).
- **Identity serialization = concatenate raw_source.** Clean nodes emit verbatim; only dirty nodes (tracked client-side via `srcId` + JSON snapshot comparison, see `frontend/src/editor/dirty.ts`) are re-serialized from PM JSON via `pmserialize.py`, and every re-serialized node is **re-parsed and canonical-compared before save** (`verify.py`) — mismatch blocks the save (422) with a diagnostic, never a corrupted file.
- I/O is bytes-in/bytes-out: per-file encoding (UTF-8/cp1251/latin-1 fallback, BOM detection) and EOL (CRLF/LF/mixed) stored as metadata and reproduced exactly.

### Opaque blocks ("source cards")
PM `opaque_block` (atom, isolating; attrs: raw, kind, label, srcId). Card shows raw text with a directive-name badge; "Edit source" opens a modal editing raw text directly — saved as an `op: "rawedit"` block (EOL-normalized, otherwise untouched). This is what makes the editor safe on constructs it doesn't understand, and — per the "poison, don't drop" principle — is also the fallback for any *whitelisted* construct that turns out to contain something the enrichment can't safely represent.

### csv-table editing — the flagship feature (2,946 instances) — **Phase 3, in progress**
- Backend `tables.py`: parses ordered raw options; parses body with Python `csv`; each supported cell payload is parsed as an **rst inline fragment** (links, `|subst|` refs, literals, `:math:`). Unsupported dialects/shapes and `:file:`-based tables stay opaque.
- **Cell-level raw preservation**: each cell keeps its original CSV token (quoting style + spacing). Dirty-table serialization re-joins cell-by-cell — clean cells/rows emit raw text verbatim; edited cells serialize inline -> rst -> CSV-quote. **Editing one cell should diff one line.**
- Frontend: `csv_table` node backed by prosemirror-tables with rich inline cell content (links clickable, `|Fluid|` shows its icon). Row/col toolbar is implemented and structural edits verify on save. Options via properties popover still pending (never reorder untouched options).
- Round-trip property tests corpus-wide: parse cells -> force-reserialize -> re-parse -> doctree-equal; plus dirty-one-cell simulations asserting single-line diffs. Hypothesis fuzzing for CSV-quoting x rst-escaping edge cases.
- This is where the `rstkit strict` gate earns its keep — it now covers supported csv-table cells (2,879 tables in the full corpus pass on 2026-07-08). Keep expanding coverage as row/column operations and options editing land.

### Substitutions & includes
- On doc open, `subst.py` scans that file's own text for `.. |name| image::`/`.. |name| replace::` definitions (corpus survey confirmed these are defined locally, not via `rst_prolog`). Editor renders `|Fluid|` as its icon (tooltip = name); unknown -> labeled chip. **Serialization always emits `|name|` untouched** (substitution refs are atoms; the reference is the data).
- `.. include::` -> opaque block for now; a dedicated card (target path, exists/missing badge, preview) is Phase 7 polish.

### Math & figures — **Phase 4, not yet built**
- `inline_math` / `math_block` atoms exist in the schema (Phase 1) but render raw LaTeX as a styled chip; KaTeX render + click-to-edit popover is Phase 4.
- `figure` node: image via `GET /api/asset` (already implemented, resolves doc-relative and srcdir-rooted paths like Sphinx does), editable caption, options popover, broken-image fallback. Paste-screenshot upload is Phase 8.

### Preview pipeline — implemented (Phase 2)
`rstkit/preview.py`: per-request docutils `html5` render of the currently-assembled text (dirty blocks included), with directive/role stubs temporarily un-registered for names docutils implements natively (so csv-tables/figures/math render for real, not as opaque debug boxes). Asset URLs rewritten through `/api/asset`. Debounced client-side (~600ms after last edit). Files >100KB fall back to unenriched (plain) display in the editor pane, but preview still works on the assembled text. Toolbar "Full Sphinx build" (real `sphinx-build`) is not yet implemented — later phase if needed.

### API surface (implemented)
```
GET  /api/project                 GET  /api/files (recursive tree)
GET  /api/doc/{path}              PUT  /api/doc/{path}   # blocks: [{op: raw|rawedit|node, ...}], base_mtime_ns -> 409 on conflict
GET  /api/asset?doc=&uri=         POST /api/preview       # same block format, tolerant (never rejects)
```
Not yet implemented: `/api/substitutions` as a standalone endpoint (currently inlined into the doc response), git status/diff/commit, file create/rename, import.

## Phased milestones (each ends usable on the real corpus)

| Phase | Scope | Acceptance criteria |
|---|---|---|
| **0 — Round-trip spike + harness** | rstkit parse, span mapping, identity serializer, CLI, EOL/BOM handling | Identity mode **100% byte-identical on all 2,093 files**; fixture corpus committed; CI runs harness on fixtures |
| **1 — Read-only browser** | FastAPI skeleton, DocumentStore, file tree, PM whitelist v1, opaque cards, substitution icons, dev.ps1 | Browse & readably view any corpus file; "save" with no edits -> zero git diff |
| **2 — Editing core + preview** | Dirty-tracking, dirty-node serialization, save w/ verify-reparse + conflict check, source-view, preview, opaque raw-edit | Typo fix -> git diff = exactly one hunk; strict mode >=95%; preview fast |
| **3 — csv-table (the crux)** | Cell inline parsing, cell-raw preservation, prosemirror-tables UI, row/col ops, options popover | Edit one cell -> diff = 1 line; corpus-wide cell test 100% doctree-equal; add row without disturbing neighbors |
| **4 — figure/image + math** | Figure nodes + asset resolution + captions; KaTeX math + edit popover | Figure-heavy page shows all images; formula edit -> 1-hunk diff |
| **5 — Git UI + file management** | Status/diff/commit panels, discard, create-from-template + rename with toctree update | Full loop create->toctree->edit->review diff->commit without leaving the browser |
| **6 — Huge files** | Outline mode >150KB: sections listed collapsed, expand-to-edit as sub-document | errors.rst (463 KB) opens fast, typing stays responsive, edit -> minimal diff |
| **7 — Whitelist round-out** | list-table, code-block/parsed-literal highlighting, admonitions, image, rst-class passthrough, include-card | Editability coverage >90% of corpus bytes; strict >=95% per new type |
| **8 — Import + niceties** | pypandoc docx/md import, paste-screenshot -> figure, polish | Representative .docx converts and saves round-trip-clean |

## Round-trip harness (permanent CI gate)
```
uv run rstkit roundtrip <docs-path> [--fail-on-diff] [--no-health]   # identity mode
uv run rstkit strict <docs-path> [--threshold N]                     # verify-reparse mode
```
- **Identity mode**: zero-dirty serialize -> byte compare. Pass = 100% byte-identical, zero normalizations. Also checks the span-partition invariant.
- **Strict mode**: for every block the editor could edit richly, simulate a dirty save (view -> PM via `pmbridge.py` -> serialize -> verify) and report the pass rate. Current: **100.00% over 13,764 blocks** including 2,879 csv-tables.

## Risk register
1. **Span-mapping fidelity** (docutils line info inconsistent for nested content) -> partition invariant checked on every parse; unmapped regions degrade to opaque cards (never data loss); verify-reparse blocks bad saves; corpus harness run continuously.
2. **csv-table cell markup** (CSV quoting x rst escaping) -> initial cell-level raw preservation confines re-serialization to edited cells; corpus strict covers supported csv-tables. Row/column operation tests exist; still needs Hypothesis fuzzing and options-edit coverage.
3. **463 KB files** -> Phase 6 outline mode built on the span model; until then oversized files fall back to unenriched plain display rather than freezing (implemented).
4. **Substitution resolution** (defined per-file, confirmed by survey) -> per-file scan; unresolved names = harmless chips; resolution never affects serialization.
5. **Cyrillic/Windows quirks** (BOM, CRLF, docutils version drift, NUL escape markers, PowerShell encoding) -> bytes-in/bytes-out with per-file EOL+BOM metadata; docutils pinned; 1,601 Cyrillic files exercised continuously by the harness; several concrete bugs already found and fixed this way (see commit `29be4e3`).

## Verification
- **Every phase**: run both `rstkit roundtrip` and `rstkit strict` against `C:\work\pradis-docs-git\docs` — must stay at their thresholds.
- **Editing phases**: end-to-end on the real corpus — open a real page, make the phase's target edit through the actual API (or UI), save, run `git -C C:\work\pradis-docs-git\docs diff` and confirm the minimal-diff acceptance criterion, then **restore the file** (`git checkout --`) since the corpus is the user's real working repo, not a fixture.
- **Backend**: `uv run pytest` (round-trip fixtures, save-path tests, API tests). **Frontend**: `pnpm build` (tsc + vite build) at minimum; Vitest/Playwright not yet set up.
