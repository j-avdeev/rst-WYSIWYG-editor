import { useCallback, useEffect, useRef, useState } from 'react'
import type { FileEntry, GetDocResponse, ProjectInfo } from './api/types'
import {
  buildStatus,
  builtUrlFor,
  createPage,
  fetchPreview,
  getDoc,
  getFileTree,
  getProject,
  importDocument,
  renamePage,
  saveDoc,
  startBuild,
  HttpError,
} from './api/client'
import { FileTree } from './panels/FileTree'
import { TocView } from './panels/TocView'
import { RightPanel } from './panels/RightPanel'
import type { PreviewData } from './panels/RightPanel'
import { Editor } from './editor/Editor'
import type { EditorApi } from './editor/Editor'
import './App.css'

type Banner =
  | { kind: 'conflict' }
  | { kind: 'error'; message: string }
  | { kind: 'saved' }
  | null

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => {
    switch (ch) {
      case '&':
        return '&amp;'
      case '<':
        return '&lt;'
      case '>':
        return '&gt;'
      case '"':
        return '&quot;'
      default:
        return '&#39;'
    }
  })
}

export default function App() {
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const [tree, setTree] = useState<FileEntry | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [doc, setDoc] = useState<GetDocResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [banner, setBanner] = useState<Banner>(null)
  const [dirtyCount, setDirtyCount] = useState(0)
  const [saving, setSaving] = useState(false)
  const [preview, setPreview] = useState<PreviewData | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [gitRefreshKey, setGitRefreshKey] = useState(0)
  const [sidebarMode, setSidebarMode] = useState<'files' | 'toc'>('files')
  const [building, setBuilding] = useState(false)
  const [buildError, setBuildError] = useState<string | null>(null)
  const [fileDialog, setFileDialog] = useState<
    | { kind: 'create'; path: string; title: string; toctree: string; error: string | null }
    | { kind: 'rename'; path: string; newPath: string; error: string | null }
    | { kind: 'import'; path: string; toctree: string; file: File | null; error: string | null }
    | null
  >(null)

  const editorApiRef = useRef<EditorApi | null>(null)
  const previewTimer = useRef<number | undefined>(undefined)
  const docRef = useRef<GetDocResponse | null>(null)
  docRef.current = doc
  const selectedRef = useRef<string | null>(null)
  selectedRef.current = selected

  useEffect(() => {
    getProject().then(setProject).catch((e) => setError(String(e)))
    getFileTree().then(setTree).catch((e) => setError(String(e)))
  }, [])

  const loadDoc = useCallback((path: string) => {
    setLoading(true)
    setError(null)
    setBanner(null)
    setPreview(null)
    setDirtyCount(0)
    getDoc(path)
      .then((d) => {
        setDoc(d)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selected) loadDoc(selected)
  }, [selected, loadDoc])

  const refreshPreviewSoon = useCallback((delayMs = 600) => {
    window.clearTimeout(previewTimer.current)
    previewTimer.current = window.setTimeout(async () => {
      const api = editorApiRef.current
      const path = selectedRef.current
      if (!api || !path) return
      setPreviewLoading(true)
      try {
        setPreview(await fetchPreview(path, api.buildBlocks()))
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e)
        setPreview({
          html: `<div class="preview-error">Preview failed: ${escapeHtml(message)}</div>`,
          text: '',
          blocks: [],
        })
      } finally {
        setPreviewLoading(false)
      }
    }, delayMs)
  }, [])

  const handleDocChanged = useCallback(() => {
    const api = editorApiRef.current
    if (api) setDirtyCount(api.dirtyCount())
    setBanner(null)
    refreshPreviewSoon()
  }, [refreshPreviewSoon])

  const handleSave = useCallback(async () => {
    const api = editorApiRef.current
    const currentDoc = docRef.current
    const path = selectedRef.current
    if (!api || !currentDoc || !path || saving) return
    setSaving(true)
    setBanner(null)
    try {
      const fresh = await saveDoc(path, currentDoc.mtime_ns, api.buildBlocks())
      setDoc(fresh)
      setDirtyCount(0)
      setBanner({ kind: 'saved' })
      setGitRefreshKey((k) => k + 1)
      refreshPreviewSoon(0)
      window.setTimeout(() => setBanner((b) => (b?.kind === 'saved' ? null : b)), 2500)
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) setBanner({ kind: 'conflict' })
      else setBanner({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }, [saving, refreshPreviewSoon])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        void handleSave()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handleSave])

  const refreshTree = useCallback(() => {
    getFileTree().then(setTree).catch((e) => setError(String(e)))
  }, [])

  const handleBuildAndView = useCallback(async () => {
    const path = selectedRef.current
    if (!path || building) return
    setBuilding(true)
    setBuildError(null)
    // open the tab NOW, inside the user gesture, so popup blockers allow it;
    // navigate it to the built page when the build finishes
    const tab = window.open('', '_blank')
    if (tab) {
      tab.document.write(
        '<title>Sphinx build…</title><body style="font-family:sans-serif;color:#555">' +
          '<h3>⚡ Building documentation…</h3><p>This tab opens the built page when done. ' +
          'First build of a large project can take a few minutes.</p>',
      )
    }
    try {
      const api = editorApiRef.current
      const currentDoc = docRef.current
      if (api && currentDoc && api.dirtyCount() > 0) {
        await handleSave()
      }
      await startBuild()
      // poll until done (up to 15 min for a cold full-corpus build)
      const deadline = Date.now() + 15 * 60_000
      let status = await buildStatus()
      while (status.state === 'running' && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1500))
        status = await buildStatus()
      }
      if (status.state === 'succeeded') {
        const url = builtUrlFor(path)
        if (tab) tab.location.href = url
        else window.open(url, '_blank')
      } else {
        tab?.close()
        setBuildError(status.log_tail.slice(-8).join('\n') || `build ${status.state}`)
      }
    } catch (e) {
      tab?.close()
      setBuildError(e instanceof Error ? e.message : String(e))
    } finally {
      setBuilding(false)
    }
  }, [building, handleSave])

  const handleWorkingTreeChanged = useCallback(
    (path: string) => {
      refreshTree()
      if (selectedRef.current === path) {
        loadDoc(path) // discarded/restored file that is open: reload or clear
      }
    },
    [refreshTree, loadDoc],
  )

  const openCreateDialog = () => {
    const dir = selected ? selected.split('/').slice(0, -1).join('/') : ''
    setFileDialog({
      kind: 'create',
      path: dir ? `${dir}/new-page.rst` : 'new-page.rst',
      title: '',
      toctree: dir ? `${dir}/index_ru.rst` : 'index.rst',
      error: null,
    })
  }

  const openRenameDialog = () => {
    if (!selected) return
    setFileDialog({ kind: 'rename', path: selected, newPath: selected, error: null })
  }

  const openImportDialog = () => {
    const dir = selected ? selected.split('/').slice(0, -1).join('/') : ''
    setFileDialog({
      kind: 'import',
      path: dir ? `${dir}/imported.rst` : 'imported.rst',
      toctree: dir ? `${dir}/index_ru.rst` : 'index.rst',
      file: null,
      error: null,
    })
  }

  const submitFileDialog = async () => {
    if (!fileDialog) return
    try {
      let newPath: string
      if (fileDialog.kind === 'create') {
        const result = await createPage(
          fileDialog.path,
          fileDialog.title,
          fileDialog.toctree.trim() || null,
        )
        newPath = result.path
      } else if (fileDialog.kind === 'import') {
        if (!fileDialog.file) return
        const result = await importDocument(
          fileDialog.path,
          fileDialog.file,
          fileDialog.toctree.trim() || null,
        )
        newPath = result.path
      } else {
        const result = await renamePage(fileDialog.path, fileDialog.newPath)
        newPath = result.path
      }
      setFileDialog(null)
      refreshTree()
      setGitRefreshKey((k) => k + 1)
      setSelected(newPath)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setFileDialog((d) => (d ? { ...d, error: message } : d))
    }
  }

  return (
    <div className="app">
      <aside className="app__sidebar">
        <div className="app__project">
          <span>{project?.name ?? '…'}</span>
          <span className="app__tree-actions">
            <button type="button" title="New page" onClick={openCreateDialog}>
              ＋
            </button>
            <button type="button" title="Import .docx / .md" onClick={openImportDialog}>
              ⇪
            </button>
            <button type="button" title="Rename selected file" disabled={!selected} onClick={openRenameDialog}>
              ✎
            </button>
          </span>
        </div>
        <div className="app__sidebar-tabs">
          <button
            type="button"
            className={sidebarMode === 'files' ? 'active' : ''}
            onClick={() => setSidebarMode('files')}
          >
            Files
          </button>
          <button
            type="button"
            className={sidebarMode === 'toc' ? 'active' : ''}
            title="Document hierarchy as readers will see it (toctree navigation)"
            onClick={() => setSidebarMode('toc')}
          >
            Contents
          </button>
        </div>
        {sidebarMode === 'files' ? (
          tree ? (
            <FileTree root={tree} selected={selected} onSelect={setSelected} />
          ) : (
            <div className="app__loading">Loading file tree…</div>
          )
        ) : (
          <TocView
            selected={selected}
            onSelect={setSelected}
            refreshKey={gitRefreshKey}
            onChanged={() => {
              refreshTree()
              setGitRefreshKey((k) => k + 1)
            }}
          />
        )}
      </aside>
      <main className="app__main">
        {!selected && <div className="app__placeholder">Select a file to edit it.</div>}
        {error && <div className="app__error">{error}</div>}
        {loading && <div className="app__loading">Loading…</div>}
        {doc && !loading && selected && (
          <>
            <div className="app__docbar">
              <span className="app__docpath">{doc.doc.path}</span>
              <span className="app__docmeta">
                {dirtyCount > 0 && <span className="app__dirty">● {dirtyCount} unsaved</span>}
                {(doc.size_bytes / 1024).toFixed(1)} KB · {doc.doc.eol.toUpperCase()} · {doc.doc.encoding}
                {!doc.enriched && ' · large file: simplified formatting'}
              </span>
              <button
                type="button"
                className="app__save"
                disabled={saving || dirtyCount === 0}
                onClick={() => void handleSave()}
              >
                {saving ? 'Saving…' : 'Save (Ctrl+S)'}
              </button>
              <button
                type="button"
                className="app__build"
                disabled={building}
                title="Run a real sphinx-build and open this page's final HTML in a new tab"
                onClick={() => void handleBuildAndView()}
              >
                {building ? 'Building…' : '⚡ Build & view'}
              </button>
            </div>
            {banner?.kind === 'conflict' && (
              <div className="app__banner app__banner--conflict">
                File changed on disk since it was opened.
                <button type="button" onClick={() => loadDoc(selected)}>
                  Reload (discards edits)
                </button>
              </div>
            )}
            {banner?.kind === 'error' && (
              <div className="app__banner app__banner--error">Save rejected: {banner.message}</div>
            )}
            {banner?.kind === 'saved' && (
              <div className="app__banner app__banner--saved">Saved.</div>
            )}
            {buildError && (
              <div className="app__banner app__banner--error">
                <span style={{ whiteSpace: 'pre-wrap', fontFamily: 'Consolas, monospace', fontSize: 12 }}>
                  Build failed:{'\n'}
                  {buildError}
                </span>
                <button type="button" onClick={() => setBuildError(null)}>
                  Dismiss
                </button>
              </div>
            )}
            <div className="app__editor-row">
              <div className="app__editor-col">
                <Editor
                  response={doc}
                  onReady={(api) => {
                    editorApiRef.current = api
                    setDirtyCount(api.dirtyCount())
                    refreshPreviewSoon(0)
                  }}
                  onDocChanged={handleDocChanged}
                />
              </div>
              <RightPanel
                data={preview}
                loading={previewLoading}
                gitRefreshKey={gitRefreshKey}
                onWorkingTreeChanged={handleWorkingTreeChanged}
              />
            </div>
          </>
        )}
      </main>

      {fileDialog && (
        <div className="file-dialog__backdrop" onClick={() => setFileDialog(null)}>
          <div className="file-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="file-dialog__title">
              {fileDialog.kind === 'create' && 'New page'}
              {fileDialog.kind === 'import' && 'Import .docx / .md'}
              {fileDialog.kind === 'rename' && 'Rename page'}
            </div>
            {fileDialog.kind === 'import' && (
              <>
                <label>
                  Document (.docx or .md — legacy .doc must be saved as .docx first)
                  <input
                    type="file"
                    accept=".docx,.md,.markdown"
                    onChange={(e) =>
                      setFileDialog({ ...fileDialog, file: e.target.files?.[0] ?? null })
                    }
                  />
                </label>
                <label>
                  Save as (.rst, relative to project root)
                  <input
                    value={fileDialog.path}
                    onChange={(e) => setFileDialog({ ...fileDialog, path: e.target.value })}
                    spellCheck={false}
                  />
                </label>
                <label>
                  Add to toctree of (optional, blank to skip)
                  <input
                    value={fileDialog.toctree}
                    onChange={(e) => setFileDialog({ ...fileDialog, toctree: e.target.value })}
                    spellCheck={false}
                  />
                </label>
                <div className="file-dialog__hint">
                  Embedded images are extracted into the page's media/ folder. The conversion
                  is a starting point — review the result in the editor before committing.
                </div>
              </>
            )}
            {fileDialog.kind === 'create' && (
              <>
                <label>
                  Path (.rst, relative to project root)
                  <input
                    value={fileDialog.path}
                    onChange={(e) => setFileDialog({ ...fileDialog, path: e.target.value })}
                    spellCheck={false}
                  />
                </label>
                <label>
                  Page title
                  <input
                    value={fileDialog.title}
                    onChange={(e) => setFileDialog({ ...fileDialog, title: e.target.value })}
                    placeholder="Заголовок страницы"
                  />
                </label>
                <label>
                  Add to toctree of (optional, blank to skip)
                  <input
                    value={fileDialog.toctree}
                    onChange={(e) => setFileDialog({ ...fileDialog, toctree: e.target.value })}
                    spellCheck={false}
                  />
                </label>
              </>
            )}
            {fileDialog.kind === 'rename' && (
              <label>
                New path
                <input
                  value={fileDialog.newPath}
                  onChange={(e) => setFileDialog({ ...fileDialog, newPath: e.target.value })}
                  spellCheck={false}
                />
              </label>
            )}
            {fileDialog.kind === 'rename' && (
              <div className="file-dialog__hint">
                Renames via git mv and updates toctree entries that point at this page.
              </div>
            )}
            {fileDialog.error && <div className="file-dialog__error">{fileDialog.error}</div>}
            <div className="file-dialog__actions">
              <button type="button" onClick={() => setFileDialog(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="primary"
                disabled={
                  (fileDialog.kind === 'create' && !fileDialog.title.trim()) ||
                  (fileDialog.kind === 'import' && !fileDialog.file)
                }
                onClick={() => void submitFileDialog()}
              >
                {fileDialog.kind === 'create' && 'Create'}
                {fileDialog.kind === 'import' && 'Import'}
                {fileDialog.kind === 'rename' && 'Rename'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
