import { useEffect, useState } from 'react'
import type { FileEntry, GetDocResponse, ProjectInfo } from './api/types'
import { getDoc, getFileTree, getProject } from './api/client'
import { FileTree } from './panels/FileTree'
import { Editor } from './editor/Editor'
import './App.css'

export default function App() {
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const [tree, setTree] = useState<FileEntry | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [doc, setDoc] = useState<GetDocResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getProject().then(setProject).catch((e) => setError(String(e)))
    getFileTree().then(setTree).catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    setError(null)
    getDoc(selected)
      .then(setDoc)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [selected])

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
        {!selected && <div className="app__placeholder">Select a file to view it.</div>}
        {error && <div className="app__error">{error}</div>}
        {loading && <div className="app__loading">Loading…</div>}
        {doc && !loading && (
          <>
            <div className="app__docbar">
              <span className="app__docpath">{doc.doc.path}</span>
              <span className="app__docmeta">
                {(doc.size_bytes / 1024).toFixed(1)} KB · {doc.doc.eol.toUpperCase()} · {doc.doc.encoding}
                {!doc.enriched && ' · large file: simplified formatting'}
                {doc.doc.parse_errors > 0 && ` · ${doc.doc.parse_errors} docutils warning(s)`}
              </span>
            </div>
            <Editor response={doc} />
          </>
        )}
      </main>
    </div>
  )
}
