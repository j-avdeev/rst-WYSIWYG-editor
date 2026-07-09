import { useEffect, useState } from 'react'
import { getToc, tocAddEntry, tocRemove, tocReorder } from '../api/client'
import type { TocNode, TocResponse } from '../api/client'
import './TocView.css'

function Row({
  node,
  depth,
  siblings,
  selected,
  onSelect,
  onChanged,
  setToc,
  setError,
}: {
  node: TocNode
  depth: number
  siblings: number
  selected: string | null
  onSelect: (path: string) => void
  onChanged: () => void
  setToc: (t: TocResponse) => void
  setError: (e: string | null) => void
}) {
  const src = node.source
  const move = async (delta: number) => {
    if (!src) return
    try {
      setToc(await tocReorder(src.file, src.toctree_index, src.position, src.position + delta))
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  const remove = async () => {
    if (!src) return
    if (!window.confirm(`Remove "${node.title}" from this toctree? The page file stays on disk.`)) return
    try {
      setToc(await tocRemove(src.file, src.toctree_index, src.position))
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div>
      <div
        className={`toc-row${selected === node.path ? ' toc-row--selected' : ''}${node.missing ? ' toc-row--missing' : ''}`}
        style={{ paddingLeft: depth * 14 + 8 }}
      >
        <button
          type="button"
          className="toc-row__title"
          title={node.path}
          onClick={() => !node.missing && onSelect(node.path)}
        >
          {node.title}
          {node.missing && <span className="toc-row__badge">missing</span>}
        </button>
        {src && (
          <span className="toc-row__actions">
            <button type="button" title="Move up" disabled={src.position === 0} onClick={() => void move(-1)}>
              ↑
            </button>
            <button
              type="button"
              title="Move down"
              disabled={src.position >= siblings - 1}
              onClick={() => void move(1)}
            >
              ↓
            </button>
            <button type="button" title="Remove from toctree" onClick={() => void remove()}>
              ✕
            </button>
          </span>
        )}
      </div>
      {node.children.map((child) => (
        <Row
          key={`${child.docname}@${child.source?.file}:${child.source?.position}`}
          node={child}
          depth={depth + 1}
          siblings={node.children.length}
          selected={selected}
          onSelect={onSelect}
          onChanged={onChanged}
          setToc={setToc}
          setError={setError}
        />
      ))}
    </div>
  )
}

export function TocView({
  selected,
  onSelect,
  refreshKey,
  onChanged,
}: {
  selected: string | null
  onSelect: (path: string) => void
  refreshKey: number
  onChanged: () => void
}) {
  const [toc, setToc] = useState<TocResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [addTarget, setAddTarget] = useState<{ docPath: string; index: string } | null>(null)

  useEffect(() => {
    getToc().then(setToc).catch((e) => setError(String(e)))
  }, [refreshKey])

  const submitAdd = async () => {
    if (!addTarget) return
    try {
      setToc(await tocAddEntry(addTarget.index, addTarget.docPath))
      setAddTarget(null)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (error) {
    return (
      <div className="toc-view">
        <div className="toc-view__error">
          {error}
          <button type="button" onClick={() => { setError(null); getToc().then(setToc).catch((e) => setError(String(e))) }}>
            Retry
          </button>
        </div>
      </div>
    )
  }
  if (!toc) return <div className="toc-view"><div className="toc-view__loading">Loading contents…</div></div>

  return (
    <div className="toc-view">
      <Row
        node={toc.tree}
        depth={0}
        siblings={1}
        selected={selected}
        onSelect={onSelect}
        onChanged={onChanged}
        setToc={setToc}
        setError={setError}
      />
      {toc.orphans.length > 0 && (
        <div className="toc-view__orphans">
          <div className="toc-view__orphans-label" title="Pages that exist on disk but are not reachable from any toctree — Sphinx will not include them in navigation">
            Not in navigation ({toc.orphans.length})
          </div>
          {toc.orphans.map((o) => (
            <div className="toc-row toc-row--orphan" key={o.docname} style={{ paddingLeft: 8 }}>
              <button type="button" className="toc-row__title" title={o.path} onClick={() => onSelect(o.path)}>
                {o.title}
              </button>
              <span className="toc-row__actions">
                <button
                  type="button"
                  title="Add to a toctree"
                  onClick={() => setAddTarget({ docPath: o.path, index: `${toc.master}.rst` })}
                >
                  ＋
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
      {addTarget && (
        <div className="toc-view__add">
          <div>
            Add <b>{addTarget.docPath}</b> to the toctree of:
          </div>
          <input
            value={addTarget.index}
            onChange={(e) => setAddTarget({ ...addTarget, index: e.target.value })}
            spellCheck={false}
          />
          <div className="toc-view__add-actions">
            <button type="button" onClick={() => setAddTarget(null)}>
              Cancel
            </button>
            <button type="button" className="primary" onClick={() => void submitAdd()}>
              Add
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
