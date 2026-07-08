import { useState } from 'react'
import type { FileEntry } from '../api/types'
import './FileTree.css'

function Node({
  entry,
  depth,
  selected,
  onSelect,
}: {
  entry: FileEntry
  depth: number
  selected: string | null
  onSelect: (path: string) => void
}) {
  const [open, setOpen] = useState(depth < 1)

  if (!entry.is_dir) {
    return (
      <div
        className={`file-tree__row file-tree__row--file${selected === entry.path ? ' file-tree__row--selected' : ''}`}
        style={{ paddingLeft: depth * 14 + 8 }}
        onClick={() => onSelect(entry.path)}
      >
        {entry.name}
      </div>
    )
  }

  return (
    <div>
      <div
        className="file-tree__row file-tree__row--dir"
        style={{ paddingLeft: depth * 14 + 8 }}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`file-tree__caret${open ? ' file-tree__caret--open' : ''}`}>▸</span>
        {entry.name}
      </div>
      {open &&
        entry.children.map((child) => (
          <Node key={child.path || child.name} entry={child} depth={depth + 1} selected={selected} onSelect={onSelect} />
        ))}
    </div>
  )
}

export function FileTree({
  root,
  selected,
  onSelect,
}: {
  root: FileEntry
  selected: string | null
  onSelect: (path: string) => void
}) {
  return (
    <div className="file-tree">
      {root.children.map((child) => (
        <Node key={child.path || child.name} entry={child} depth={0} selected={selected} onSelect={onSelect} />
      ))}
    </div>
  )
}
