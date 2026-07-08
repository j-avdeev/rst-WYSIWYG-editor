import { useCallback, useEffect, useState } from 'react'
import { gitCommit, gitDiff, gitDiscard, gitStatus } from '../api/client'
import type { GitFileStatus } from '../api/client'
import './GitPanel.css'

const STATUS_LABEL: Record<string, string> = {
  M: 'modified',
  A: 'added',
  D: 'deleted',
  R: 'renamed',
  '??': 'new',
}

function DiffView({ diff }: { diff: string }) {
  if (!diff.trim()) return <div className="git-panel__empty">No changes.</div>
  return (
    <pre className="git-diff">
      {diff.split('\n').map((line, i) => {
        let cls = ''
        if (line.startsWith('+') && !line.startsWith('+++')) cls = 'git-diff__add'
        else if (line.startsWith('-') && !line.startsWith('---')) cls = 'git-diff__del'
        else if (line.startsWith('@@')) cls = 'git-diff__hunk'
        else if (line.startsWith('diff ') || line.startsWith('index ')) cls = 'git-diff__meta'
        return (
          <div key={i} className={cls}>
            {line || ' '}
          </div>
        )
      })}
    </pre>
  )
}

export function GitPanel({
  refreshKey,
  onWorkingTreeChanged,
}: {
  refreshKey: number
  onWorkingTreeChanged: (path: string) => void
}) {
  const [branch, setBranch] = useState('')
  const [files, setFiles] = useState<GitFileStatus[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [diffFor, setDiffFor] = useState<string | null>(null)
  const [diff, setDiff] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastCommit, setLastCommit] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const status = await gitStatus()
      setBranch(status.branch)
      setFiles(status.files)
      setSelected(new Set(status.files.map((f) => f.path)))
      if (diffFor && !status.files.some((f) => f.path === diffFor)) {
        setDiffFor(null)
        setDiff('')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diffFor])

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  const showDiff = async (path: string) => {
    setDiffFor(path)
    setDiff('…')
    try {
      setDiff((await gitDiff(path)).diff)
    } catch (e) {
      setDiff(`failed to load diff: ${e instanceof Error ? e.message : e}`)
    }
  }

  const toggle = (path: string) => {
    const next = new Set(selected)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setSelected(next)
  }

  const commit = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    setLastCommit(null)
    try {
      const result = await gitCommit(message, [...selected])
      setMessage('')
      setLastCommit(result.head)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const discard = async (path: string) => {
    if (!window.confirm(`Discard all changes to ${path}? This cannot be undone.`)) return
    setBusy(true)
    setError(null)
    try {
      await gitDiscard(path)
      await refresh()
      onWorkingTreeChanged(path)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="git-panel">
      <div className="git-panel__head">
        <span className="git-panel__branch">⎇ {branch || '…'}</span>
        <button type="button" onClick={() => void refresh()} title="Refresh status">
          ↻
        </button>
      </div>
      {error && <div className="git-panel__error">{error}</div>}
      {lastCommit && <div className="git-panel__committed">Committed: {lastCommit}</div>}

      {files.length === 0 && !error && <div className="git-panel__empty">Working tree clean.</div>}

      {files.map((f) => (
        <div key={f.path} className={`git-file${diffFor === f.path ? ' git-file--active' : ''}`}>
          <input
            type="checkbox"
            checked={selected.has(f.path)}
            onChange={() => toggle(f.path)}
            title="Include in commit"
          />
          <button type="button" className="git-file__path" onClick={() => void showDiff(f.path)}>
            <span className={`git-file__status git-file__status--${f.status === '??' ? 'new' : f.status[0]}`}>
              {STATUS_LABEL[f.status] ?? f.status}
            </span>
            {f.path}
          </button>
          <button
            type="button"
            className="git-file__discard"
            title="Discard changes"
            disabled={busy}
            onClick={() => void discard(f.path)}
          >
            ⟲
          </button>
        </div>
      ))}

      {diffFor && (
        <>
          <div className="git-panel__diff-title">{diffFor}</div>
          <DiffView diff={diff} />
        </>
      )}

      {files.length > 0 && (
        <div className="git-panel__commit">
          <textarea
            placeholder="Commit message…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <button
            type="button"
            className="primary"
            disabled={busy || !message.trim() || selected.size === 0}
            onClick={() => void commit()}
          >
            Commit {selected.size} file{selected.size === 1 ? '' : 's'}
          </button>
        </div>
      )}
    </div>
  )
}
