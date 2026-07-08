import { useEffect, useRef, useState } from 'react'
import { EditorState } from 'prosemirror-state'
import { EditorView } from 'prosemirror-view'
import { Node } from 'prosemirror-model'
import { keymap } from 'prosemirror-keymap'
import { history, undo, redo } from 'prosemirror-history'
import { baseKeymap, toggleMark } from 'prosemirror-commands'
import { gapCursor } from 'prosemirror-gapcursor'
import type { GetDocResponse } from '../api/types'
import { schema } from './schema'
import { edDocToPMDoc } from './convert'
import { DirtyTracker } from './dirty'
import type { SaveBlock } from './dirty'
import './editor.css'

export interface EditorApi {
  buildBlocks(): SaveBlock[]
  dirtyCount(): number
}

interface OpaqueEditRequest {
  pos: number
  raw: string
  label: string
}

class OpaqueBlockView {
  dom: HTMLElement

  constructor(
    node: Node,
    getPos: () => number | undefined,
    onEdit: (req: OpaqueEditRequest) => void,
  ) {
    const card = document.createElement('div')
    card.className = 'opaque-block'
    const header = document.createElement('div')
    header.className = 'opaque-block__label'
    const title = document.createElement('span')
    title.textContent = String(node.attrs.label || node.attrs.kind)
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'opaque-block__edit'
    button.textContent = 'Edit source'
    button.addEventListener('mousedown', (e) => e.preventDefault())
    button.addEventListener('click', () => {
      const pos = getPos()
      if (pos !== undefined) {
        onEdit({ pos, raw: String(node.attrs.raw), label: String(node.attrs.label || node.attrs.kind) })
      }
    })
    header.append(title, button)
    const pre = document.createElement('pre')
    pre.textContent = String(node.attrs.raw)
    card.append(header, pre)
    this.dom = card
  }
}

export function Editor({
  response,
  onReady,
  onDocChanged,
}: {
  response: GetDocResponse
  onReady?: (api: EditorApi) => void
  onDocChanged?: () => void
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [opaqueEdit, setOpaqueEdit] = useState<OpaqueEditRequest | null>(null)
  const [draft, setDraft] = useState('')
  const viewRef = useRef<EditorView | null>(null)

  useEffect(() => {
    if (!hostRef.current) return

    let pmDoc: Node
    try {
      const json = edDocToPMDoc(response.doc, response.substitutions)
      pmDoc = Node.fromJSON(schema, json)
    } catch (err) {
      console.error('failed to build document, showing raw source', err)
      pmDoc = schema.node('doc', null, [
        schema.node('opaque_block', {
          raw: response.doc.nodes.map((n) => n.raw_source).join(''),
          kind: 'parse-error',
          label: 'Could not render — showing raw source',
        }),
      ])
    }

    const tracker = new DirtyTracker()
    tracker.init(response.doc, pmDoc)

    const state = EditorState.create({
      doc: pmDoc,
      schema,
      plugins: [
        history(),
        gapCursor(),
        keymap({
          'Mod-z': undo,
          'Mod-y': redo,
          'Mod-Shift-z': redo,
          'Mod-b': toggleMark(schema.marks.strong),
          'Mod-i': toggleMark(schema.marks.em),
          'Mod-e': toggleMark(schema.marks.code),
        }),
        keymap(baseKeymap),
      ],
    })

    const view: EditorView = new EditorView(hostRef.current, {
      state,
      nodeViews: {
        opaque_block: (node, _view, getPos) =>
          new OpaqueBlockView(node, getPos as () => number | undefined, (req) => {
            setDraft(req.raw)
            setOpaqueEdit(req)
          }),
      },
      dispatchTransaction: (tr) => {
        view.updateState(view.state.apply(tr))
        if (tr.docChanged) onDocChanged?.()
      },
    })
    viewRef.current = view

    onReady?.({
      buildBlocks: () => tracker.buildBlocks(view.state.doc),
      dirtyCount: () => tracker.dirtyCount(view.state.doc),
    })

    return () => {
      view.destroy()
      viewRef.current = null
    }
  }, [response])

  const commitOpaqueEdit = () => {
    const view = viewRef.current
    if (!view || !opaqueEdit) return
    const node = view.state.doc.nodeAt(opaqueEdit.pos)
    if (node && node.type.name === 'opaque_block') {
      view.dispatch(
        view.state.tr.setNodeMarkup(opaqueEdit.pos, undefined, {
          ...node.attrs,
          raw: draft,
        }),
      )
    }
    setOpaqueEdit(null)
  }

  return (
    <div className="editor-wrap">
      <div className="editor-host" ref={hostRef} />
      {opaqueEdit && (
        <div className="opaque-modal__backdrop" onClick={() => setOpaqueEdit(null)}>
          <div className="opaque-modal" onClick={(e) => e.stopPropagation()}>
            <div className="opaque-modal__title">Edit source — {opaqueEdit.label}</div>
            <textarea
              className="opaque-modal__textarea"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
            />
            <div className="opaque-modal__actions">
              <button type="button" onClick={() => setOpaqueEdit(null)}>
                Cancel
              </button>
              <button type="button" className="primary" onClick={commitOpaqueEdit}>
                Apply
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
