import { useEffect, useRef } from 'react'
import { EditorState } from 'prosemirror-state'
import { EditorView } from 'prosemirror-view'
import { Node } from 'prosemirror-model'
import { keymap } from 'prosemirror-keymap'
import { history } from 'prosemirror-history'
import { baseKeymap } from 'prosemirror-commands'
import type { GetDocResponse } from '../api/types'
import { schema } from './schema'
import { edDocToPMDoc } from './convert'
import './editor.css'

export function Editor({ response }: { response: GetDocResponse }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)

  useEffect(() => {
    if (!hostRef.current) return

    let pmDoc: Node
    try {
      const json = edDocToPMDoc(response.doc, response.substitutions)
      pmDoc = Node.fromJSON(schema, json)
    } catch (err) {
      // Should be unreachable — convert.ts validates every top-level node —
      // but a read-only viewer must never hard-crash on a real corpus file.
      console.error('failed to build document, showing raw source', err)
      pmDoc = schema.node('doc', null, [
        schema.node('opaque_block', {
          raw: response.doc.nodes.map((n) => n.raw_source).join(''),
          kind: 'parse-error',
          label: 'Could not render — showing raw source',
        }),
      ])
    }

    const state = EditorState.create({
      doc: pmDoc,
      schema,
      plugins: [history(), keymap(baseKeymap)],
    })

    const view = new EditorView(hostRef.current, {
      state,
      editable: () => false,
    })
    viewRef.current = view
    return () => view.destroy()
  }, [response])

  return <div className="editor-host" ref={hostRef} />
}
