import type { RefObject } from 'react'
import { SNIPPET_GROUPS } from './latex-snippets'
import type { Snippet } from './latex-snippets'
import './latex-toolbar.css'

/** Wraps the current selection (or opens a cursor slot) in a controlled
 * <textarea>, mirroring how every LaTeX-snippet-palette editor behaves. */
export function insertSnippet(
  textareaRef: RefObject<HTMLTextAreaElement | null>,
  value: string,
  setValue: (v: string) => void,
  snippet: Snippet,
): void {
  const el = textareaRef.current
  const start = el?.selectionStart ?? value.length
  const end = el?.selectionEnd ?? value.length
  const selected = value.slice(start, end)

  let next: string
  let caretPos: number
  if (snippet.insert !== undefined) {
    next = value.slice(0, start) + snippet.insert + value.slice(end)
    caretPos = start + snippet.insert.length
  } else {
    const before = snippet.before ?? ''
    const after = snippet.after ?? ''
    next = value.slice(0, start) + before + selected + after + value.slice(end)
    caretPos = selected ? start + before.length + selected.length + after.length : start + before.length
  }

  setValue(next)
  requestAnimationFrame(() => {
    el?.focus()
    el?.setSelectionRange(caretPos, caretPos)
  })
}

export function LatexToolbar({
  textareaRef,
  value,
  setValue,
}: {
  textareaRef: RefObject<HTMLTextAreaElement | null>
  value: string
  setValue: (v: string) => void
}) {
  return (
    <div className="latex-toolbar">
      {SNIPPET_GROUPS.map((group) => (
        <div className="latex-toolbar__group" key={group.name}>
          <div className="latex-toolbar__group-label">{group.name}</div>
          <div className="latex-toolbar__buttons">
            {group.items.map((snippet) => (
              <button
                key={snippet.label + (snippet.insert ?? snippet.before ?? '')}
                type="button"
                title={snippet.title ?? snippet.label}
                className="latex-toolbar__btn"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => insertSnippet(textareaRef, value, setValue, snippet)}
              >
                {snippet.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
