import { useCallback, useEffect, useRef, useState } from 'react'
import type { FileEntry, GetDocResponse, ProjectInfo } from './api/types'
import { fetchPreview, getDoc, getFileTree, getProject, saveDoc, HttpError } from './api/client'
import { FileTree } from './panels/FileTree'
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

  return (
    <div className="app">
      <aside className="app__sidebar">
        <div className="app__project">{project?.name ?? '…'}</div>
        {tree ? (
          <FileTree root={tree} selected={selected} onSelect={setSelected} />
        ) : (
          <div className="app__loading">Loading file tree…</div>
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
              <RightPanel data={preview} loading={previewLoading} />
            </div>
          </>
        )}
      </main>
    </div>
  )
}
