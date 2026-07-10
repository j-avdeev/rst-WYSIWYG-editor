# rst WYSIWYG Editor

A local, browser-based WYSIWYG editor for [Sphinx](https://www.sphinx-doc.org/)
`.rst` documentation. Made for documentation editors, not programmers: you
edit pages visually, and the tool takes care of reStructuredText syntax,
image files, and git.

**The core promise:** anything you don't touch is saved back *byte-for-byte
identical*, and every edited block is verified by re-parsing before it is
written. A save that would corrupt a file is rejected instead of written.
All changes go through git, so nothing is ever lost.

## What you can do

- **Edit text** — headings, paragraphs, bold/italic/code (Ctrl+B / Ctrl+I / Ctrl+E), lists
- **Edit tables** — `csv-table` directives become real tables: edit cells with
  links and icons in them, add/remove rows and columns, edit caption and
  options (⚙ Options)
- **Formulas** — click any formula to edit it with a live preview and a LaTeX
  symbol palette (Greek letters, fractions, integrals, brackets, …); insert
  new ones with ∑ Formula
- **Images** — paste from clipboard, drag & drop, or pick a file; the image is
  copied into the page's `media/` folder and the `figure` directive is written
  for you. On any image card: **⟳ rotate 90°, ⇄/⇅ flip, ✂ crop, Replace image**
- **Import Word/Markdown** — ⇪ Import converts a `.docx` or `.md` file to a new
  .rst page (embedded images are extracted automatically). Legacy `.doc` must
  be re-saved as `.docx` in Word first
- **Git built in** — the Git tab shows your changed files with colored diffs;
  commit selected files with a message, or discard a file's changes
- **⚡ Build & view** — runs a real `sphinx-build` and opens the final themed
  HTML of the page you are editing in a new tab
- **Contents tab** — the table of contents as readers see it, with real page
  titles: reorder or remove entries, and see "not in navigation" (orphan)
  pages with one-click fixing
- **New pages** — ＋ creates a page and registers it in a toctree; ✎ renames a
  page (updating every toctree that points at it, preserving git history)

Anything the editor does not understand yet is shown as a gray "source card"
that you can still edit as raw text — it is preserved exactly, never mangled.

## Requirements

- Windows 10/11
- [git](https://git-scm.com/download/win) — your documentation must be a git checkout
- [uv](https://docs.astral.sh/uv/) — manages Python for you; install once with:
  ```powershell
  winget install astral-sh.uv
  ```
- Internet connection on first launch (downloads Python packages once)
- Any modern browser; Chrome or Edge recommended (smarter file dialogs)

## Install and run (from a release)

1. Download the `.zip` from the [Releases](../../releases) page.
2. Unpack it anywhere (e.g. `C:\Tools\rst-editor`).
3. Run, pointing at your Sphinx source directory (the folder with `conf.py`):
   ```powershell
   powershell -File start.ps1 -Root "C:\work\pradis-docs-git\docs\pradis-sphinx-doc"
   ```
4. Your browser opens the editor automatically. First launch takes a few
   minutes (one-time package download); after that it starts in seconds.

To update: download the new zip and unpack it over the old folder.

## Install and run (from source)

```powershell
git clone https://github.com/j-avdeev/rst-WYSIWYG-editor
cd rst-WYSIWYG-editor\frontend
pnpm install
pnpm build        # requires Node 20+ / pnpm; one time
cd ..
powershell -File start.ps1 -Root "C:\path\to\your\sphinx\source"
```

## Known limitations

- `list-table`, `code-block`, admonitions and `include` blocks edit as raw
  source cards (rich editing planned)
- Very large files (e.g. a 463 KB reference page) open with simplified
  formatting
- If a save is rejected with an error banner, the file on disk was **not**
  touched — adjust the flagged block or edit it as raw source
- Full file-dialog integration ("Connect docs folder") works in Chrome/Edge
  only; other browsers get a standard file picker

## Troubleshooting

- **First launch fails with "cannot find the path specified"** — unpack the
  editor into a short path like `C:\Tools\rst-editor` (deeply nested folders
  hit Windows' 260-character path limit during the one-time package install)
- **Port already in use** — start with another port: `start.ps1 -Root ... -Port 8020`
- **"File changed on disk" banner** — someone (or another tool) modified the
  file while you were editing; reload the page from the banner
- **Where is the built site?** — `build/html` inside your docs source folder
  (the same place `sphinx-build` normally puts it)
- **Import fails on a `.doc` file** — open it in Word, save as `.docx`, retry

---

## Development

Dev mode (hot reload for both backend and frontend):

```powershell
powershell -File scripts\dev.ps1     # backend :8010 + Vite :5173
```

Quality gates — run after any change to `backend/src/rstkit/` and keep green:

```powershell
cd backend
uv run pytest                                          # unit + fixture corpus + API tests
uv run rstkit roundtrip C:\path\to\docs                # identity: 100% byte-identical
uv run rstkit strict C:\path\to\docs                   # verify-reparse: >=95% (currently 100%)
```

Architecture, phase status, and design principles: **[PLAN.md](PLAN.md)**.
Stack: Python/FastAPI + docutils (pinned 0.21.2) on the backend, ProseMirror +
React + Vite on the frontend, pandoc for import, Pillow for image edits,
Sphinx 8.2.3 for real builds.
