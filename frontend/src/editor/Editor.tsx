import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { EditorState } from 'prosemirror-state'
import type { Command } from 'prosemirror-state'
import { EditorView } from 'prosemirror-view'
import { Node } from 'prosemirror-model'
import { keymap } from 'prosemirror-keymap'
import { history, undo, redo } from 'prosemirror-history'
import { baseKeymap, toggleMark } from 'prosemirror-commands'
import { gapCursor } from 'prosemirror-gapcursor'
import katex from 'katex'
import {
  addColumnAfter,
  addColumnBefore,
  addRowAfter,
  addRowBefore,
  columnResizing,
  deleteColumn,
  deleteRow,
  isInTable,
  tableEditing,
} from 'prosemirror-tables'
import type { GetDocResponse } from '../api/types'
import { assetUrl, uploadAsset } from '../api/client'
import { schema } from './schema'
import { edDocToPMDoc } from './convert'
import { DirtyTracker } from './dirty'
import type { SaveBlock } from './dirty'
import { LatexToolbar } from './LatexToolbar'
import { pickImageFileViaFsAccess } from './file-picker'
import {
  getMediaDirHint,
  hasStoredProjectFolder,
  requestProjectFolderAccess,
  supportsFolderAccess,
} from './project-folder'
import { MathPreview } from './MathPreview'
import './editor.css'

export interface EditorApi {
  buildBlocks(): SaveBlock[]
  dirtyCount(): number
}

interface OpaqueEditRequest {
  pos: number
  raw: string
  label: string
  kind: string
}

type MathEditRequest = { mode: 'inline'; pos: number; tex: string } | { mode: 'insert' }

const IMAGE_RE = /^([ \t]*\.\.[ \t]+(?:figure|image)::[ \t]*)(\S+)/m

function imageUriFrom(raw: string): string | null {
  return IMAGE_RE.exec(raw)?.[2] ?? null
}

function replaceImageUri(raw: string, newUri: string): string {
  return raw.replace(IMAGE_RE, (_m, prefix: string) => prefix + newUri)
}

/** Best-effort LaTeX body extraction from a `.. math::` directive's raw
 * source, for the live preview only — never used to produce saved text. */
function mathBodyFromDirective(raw: string): string {
  const lines = raw.replace(/\r\n/g, '\n').split('\n')
  const bodyLines = lines
    .slice(1) // drop the ".. math::" header line
    .filter((l) => !/^\s*:[\w-]+:/.test(l)) // drop option lines
  const indented = bodyLines.filter((l) => l.trim())
  if (!indented.length) return ''
  const minIndent = Math.min(...indented.map((l) => l.length - l.trimStart().length))
  return indented.map((l) => l.slice(minIndent)).join(' ').trim()
}

class OpaqueBlockView {
  dom: HTMLElement

  constructor(
    node: Node,
    getPos: () => number | undefined,
    docPath: string,
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
        onEdit({
          pos,
          raw: String(node.attrs.raw),
          label: String(node.attrs.label || node.attrs.kind),
          kind: String(node.attrs.kind),
        })
      }
    })
    header.append(title, button)
    card.append(header)

    const kind = String(node.attrs.kind)
    if (kind === 'figure' || kind === 'image') {
      const uri = imageUriFrom(String(node.attrs.raw))
      if (uri) {
        const img = document.createElement('img')
        img.className = 'opaque-block__thumb'
        img.src = assetUrl(docPath, uri)
        img.alt = uri
        img.onerror = () => img.remove()
        card.append(img)
      }
    }

    const pre = document.createElement('pre')
    pre.textContent = String(node.attrs.raw)
    card.append(pre)
    this.dom = card
  }
}

function renderInlineMathInto(el: HTMLElement, tex: string) {
  try {
    if (tex.trim()) {
      katex.render(tex, el, { throwOnError: true })
      el.className = 'inline-math-view'
    } else {
      el.textContent = '⨍(x)'
      el.className = 'inline-math-view inline-math-view--empty'
    }
  } catch {
    el.textContent = `:math:\`${tex}\``
    el.className = 'inline-math-view inline-math-view--error'
  }
}

class InlineMathView {
  dom: HTMLElement

  constructor(node: Node, getPos: () => number | undefined, onEdit: (pos: number, tex: string) => void) {
    const el = document.createElement('span')
    el.title = 'Click to edit formula'
    el.addEventListener('mousedown', (e) => e.preventDefault())
    el.addEventListener('click', () => {
      const pos = getPos()
      if (pos !== undefined) onEdit(pos, String(node.attrs.tex))
    })
    renderInlineMathInto(el, String(node.attrs.tex))
    this.dom = el
  }
}

async function pickImageForDoc(docPath: string) {
  const hint = await getMediaDirHint(docPath)
  return pickImageFileViaFsAccess(hint)
}

function MainToolbar({
  docPath,
  folderConnected,
  onConnectFolder,
  onInsertImage,
  onInsertFormula,
}: {
  docPath: string
  folderConnected: boolean
  onConnectFolder: () => void
  onInsertImage: (file: File) => void
  onInsertFormula: () => void
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  return (
    <div className="main-toolbar" aria-label="Insert controls">
      <button
        type="button"
        title="Insert image"
        onMouseDown={(e) => e.preventDefault()}
        onClick={async () => {
          const result = await pickImageForDoc(docPath)
          if (result.status === 'picked') onInsertImage(result.file)
          else if (result.status === 'unsupported') fileInputRef.current?.click()
        }}
      >
        🖼 Image
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/svg+xml,image/bmp,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onInsertImage(file)
          e.target.value = ''
        }}
      />
      {supportsFolderAccess() && !folderConnected && (
        <button
          type="button"
          title="Grant access to your docs folder so image pickers open in the right place automatically"
          onMouseDown={(e) => e.preventDefault()}
          onClick={onConnectFolder}
        >
          📁 Connect docs folder
        </button>
      )}
      <button
        type="button"
        title="Insert formula"
        onMouseDown={(e) => e.preventDefault()}
        onClick={onInsertFormula}
      >
        ∑ Formula
      </button>
    </div>
  )
}

// csv meta carried on the PM table node (mirror of backend tables.py view)
export interface CsvOption {
  name: string
  value: string
  raw?: string
}

export interface CsvMeta {
  kind: string
  caption: string
  directive: string
  indent: string
  delimiter: string
  quote: string
  options: CsvOption[]
  hasHeader: boolean
}

/** The csv table node surrounding the selection, or null. */
function findCsvTable(state: EditorState): { pos: number; meta: CsvMeta } | null {
  const { $from } = state.selection
  for (let depth = $from.depth; depth > 0; depth--) {
    const node = $from.node(depth)
    if (node.type.name === 'table' && (node.attrs.csv as CsvMeta | null)?.kind === 'csv_table') {
      return { pos: $from.before(depth), meta: node.attrs.csv as CsvMeta }
    }
  }
  return null
}

function TableToolbar({
  viewRef,
  onOpenOptions,
}: {
  viewRef: RefObject<EditorView | null>
  onOpenOptions: () => void
}) {
  const run = (command: Command) => {
    const view = viewRef.current
    if (!view) return
    command(view.state, view.dispatch, view)
    view.focus()
  }

  return (
    <div className="table-toolbar" aria-label="Table controls">
      <button type="button" title="Insert row above" onMouseDown={(e) => e.preventDefault()} onClick={() => run(addRowBefore)}>
        Row +
      </button>
      <button type="button" title="Insert row below" onMouseDown={(e) => e.preventDefault()} onClick={() => run(addRowAfter)}>
        + Row
      </button>
      <button type="button" title="Delete selected row" onMouseDown={(e) => e.preventDefault()} onClick={() => run(deleteRow)}>
        Row -
      </button>
      <span className="table-toolbar__separator" />
      <button type="button" title="Insert column left" onMouseDown={(e) => e.preventDefault()} onClick={() => run(addColumnBefore)}>
        Col +
      </button>
      <button type="button" title="Insert column right" onMouseDown={(e) => e.preventDefault()} onClick={() => run(addColumnAfter)}>
        + Col
      </button>
      <button type="button" title="Delete selected column" onMouseDown={(e) => e.preventDefault()} onClick={() => run(deleteColumn)}>
        Col -
      </button>
      <span className="table-toolbar__separator" />
      <button type="button" title="Edit caption and directive options" onMouseDown={(e) => e.preventDefault()} onClick={onOpenOptions}>
        ⚙ Options
      </button>
    </div>
  )
}

const KNOWN_CSV_OPTIONS = [
  'widths', 'width', 'align', 'header-rows', 'stub-columns', 'delim', 'quote', 'keepspace', 'escape', 'class', 'name',
]

interface TableOptionsDraft {
  pos: number
  meta: CsvMeta
  caption: string
  options: { name: string; value: string; origIndex: number | null }[]
}

function TableOptionsModal({
  draft,
  onChange,
  onCancel,
  onApply,
}: {
  draft: TableOptionsDraft
  onChange: (d: TableOptionsDraft) => void
  onCancel: () => void
  onApply: () => void
}) {
  const setOption = (i: number, field: 'name' | 'value', v: string) => {
    const options = draft.options.map((o, j) => (j === i ? { ...o, [field]: v } : o))
    onChange({ ...draft, options })
  }
  return (
    <div className="opaque-modal__backdrop" onClick={onCancel}>
      <div className="opaque-modal" onClick={(e) => e.stopPropagation()}>
        <div className="opaque-modal__title">Table options — .. csv-table::</div>
        <div className="table-options">
          <label className="table-options__row">
            <span className="table-options__label">Caption</span>
            <input
              value={draft.caption}
              onChange={(e) => onChange({ ...draft, caption: e.target.value })}
              placeholder="(no caption)"
            />
          </label>
          {draft.options.map((opt, i) =>
            opt.name === 'header' ? (
              <div className="table-options__row" key={i}>
                <span className="table-options__label">:header:</span>
                <span className="table-options__note">edited via the first table row</span>
              </div>
            ) : (
              <div className="table-options__row" key={i}>
                <input
                  className="table-options__name"
                  value={opt.name}
                  list="csv-option-names"
                  onChange={(e) => setOption(i, 'name', e.target.value)}
                  placeholder="option"
                />
                <input
                  value={opt.value}
                  onChange={(e) => setOption(i, 'value', e.target.value)}
                  placeholder="value"
                />
                <button
                  type="button"
                  title="Remove option"
                  onClick={() =>
                    onChange({ ...draft, options: draft.options.filter((_, j) => j !== i) })
                  }
                >
                  ✕
                </button>
              </div>
            ),
          )}
          <datalist id="csv-option-names">
            {KNOWN_CSV_OPTIONS.map((n) => (
              <option value={n} key={n} />
            ))}
          </datalist>
          <button
            type="button"
            className="table-options__add"
            onClick={() =>
              onChange({
                ...draft,
                options: [...draft.options, { name: '', value: '', origIndex: null }],
              })
            }
          >
            + Add option
          </button>
          <div className="table-options__hint">
            Changing :delim: or :quote: rewrites the whole table body in the new dialect.
          </div>
        </div>
        <div className="opaque-modal__actions">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="primary" onClick={onApply}>
            Apply
          </button>
        </div>
      </div>
    </div>
  )
}

function isImageFile(file: File): boolean {
  return file.type.startsWith('image/')
}

function ImageReplaceControl({
  docPath,
  raw,
  onReplace,
}: {
  docPath: string
  raw: string
  onReplace: (file: File) => void
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uri = imageUriFrom(raw)

  return (
    <div className="image-replace">
      {uri ? (
        <img className="image-replace__thumb" src={assetUrl(docPath, uri)} alt={uri} />
      ) : (
        <div className="image-replace__thumb image-replace__thumb--missing">no image path found</div>
      )}
      <button
        type="button"
        onClick={async () => {
          const result = await pickImageForDoc(docPath)
          if (result.status === 'picked') onReplace(result.file)
          else if (result.status === 'unsupported') fileInputRef.current?.click()
        }}
      >
        Replace image…
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/svg+xml,image/bmp,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onReplace(file)
          e.target.value = ''
        }}
      />
    </div>
  )
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
  const [mathEdit, setMathEdit] = useState<MathEditRequest | null>(null)
  const [mathDraft, setMathDraft] = useState('')
  const [tableActive, setTableActive] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [folderConnected, setFolderConnected] = useState(false)
  const [tableOpts, setTableOpts] = useState<TableOptionsDraft | null>(null)
  const viewRef = useRef<EditorView | null>(null)
  const opaqueTextareaRef = useRef<HTMLTextAreaElement>(null)
  const mathTextareaRef = useRef<HTMLTextAreaElement>(null)
  const docPath = response.doc.path

  useEffect(() => {
    hasStoredProjectFolder().then(setFolderConnected)
  }, [])

  const connectFolder = async () => {
    const ok = await requestProjectFolderAccess()
    if (ok) setFolderConnected(true)
  }

  const insertImageNode = (uri: string) => {
    const view = viewRef.current
    if (!view) return
    const raw = `.. figure:: ${uri}\n\n   \n`
    const node = schema.node('opaque_block', { raw, kind: 'figure', label: '.. figure::', srcId: null })
    const { $from } = view.state.selection
    const insertPos = $from.depth >= 1 ? $from.after(1) : view.state.doc.content.size
    try {
      view.dispatch(view.state.tr.insert(insertPos, node))
    } catch (err) {
      console.error('failed to insert image block', err)
    }
    view.focus()
  }

  const handleInsertImage = async (file: File) => {
    if (!isImageFile(file)) {
      setUploadError('Not an image file.')
      return
    }
    setUploadError(null)
    try {
      const { uri } = await uploadAsset(docPath, file)
      insertImageNode(uri)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleReplaceImage = async (file: File) => {
    if (!isImageFile(file)) {
      setUploadError('Not an image file.')
      return
    }
    setUploadError(null)
    try {
      const { uri } = await uploadAsset(docPath, file)
      setDraft((current) => replaceImageUri(current, uri))
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err))
    }
  }

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
        columnResizing(),
        tableEditing(),
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
          new OpaqueBlockView(node, getPos as () => number | undefined, docPath, (req) => {
            setDraft(req.raw)
            setOpaqueEdit(req)
          }),
        inline_math: (node, _view, getPos) =>
          new InlineMathView(node, getPos as () => number | undefined, (pos, tex) => {
            setMathDraft(tex)
            setMathEdit({ mode: 'inline', pos, tex })
          }),
      },
      handleDOMEvents: {
        paste: (_view, event: ClipboardEvent) => {
          const file = Array.from(event.clipboardData?.files ?? []).find(isImageFile)
          if (!file) return false
          event.preventDefault()
          void handleInsertImage(file)
          return true
        },
        drop: (_view, event: DragEvent) => {
          const file = Array.from(event.dataTransfer?.files ?? []).find(isImageFile)
          if (!file) return false
          event.preventDefault()
          void handleInsertImage(file)
          return true
        },
      },
      dispatchTransaction: (tr) => {
        const nextState = view.state.apply(tr)
        view.updateState(nextState)
        setTableActive(isInTable(nextState))
        if (tr.docChanged) onDocChanged?.()
      },
    })
    viewRef.current = view
    setTableActive(isInTable(view.state))

    onReady?.({
      buildBlocks: () => tracker.buildBlocks(view.state.doc),
      dirtyCount: () => tracker.dirtyCount(view.state.doc),
    })

    return () => {
      view.destroy()
      viewRef.current = null
      setTableActive(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const openTableOptions = () => {
    const view = viewRef.current
    if (!view) return
    const found = findCsvTable(view.state)
    if (!found) return
    setTableOpts({
      pos: found.pos,
      meta: found.meta,
      caption: found.meta.caption ?? '',
      options: (found.meta.options ?? []).map((o, i) => ({
        name: o.name,
        value: o.value,
        origIndex: i,
      })),
    })
  }

  const applyTableOptions = () => {
    const view = viewRef.current
    if (!view || !tableOpts) return
    const node = view.state.doc.nodeAt(tableOpts.pos)
    if (!node || node.type.name !== 'table') {
      setTableOpts(null)
      return
    }
    const orig = tableOpts.meta
    const options: CsvOption[] = []
    for (const o of tableOpts.options) {
      const name = o.name.trim()
      if (!name) continue
      const original = o.origIndex !== null ? orig.options[o.origIndex] : null
      if (original && original.name === name && original.value === o.value) {
        options.push(original) // untouched: keeps its raw line byte-identical
      } else {
        options.push({ name, value: o.value, raw: '' }) // re-emitted canonically
      }
    }
    const captionChanged = tableOpts.caption !== orig.caption
    const csv: CsvMeta = {
      ...orig,
      caption: tableOpts.caption,
      directive: captionChanged ? '' : orig.directive,
      options,
      // delimiter/quote stay at their PARSE-time values on purpose: the
      // backend compares them against the options' effective dialect to
      // decide whether raw-preservation is still safe
    }
    view.dispatch(
      view.state.tr.setNodeMarkup(tableOpts.pos, undefined, { ...node.attrs, csv }),
    )
    setTableOpts(null)
    view.focus()
  }

  const commitMathEdit = () => {
    const view = viewRef.current
    if (!view || !mathEdit) return
    if (mathEdit.mode === 'inline') {
      const node = view.state.doc.nodeAt(mathEdit.pos)
      if (node && node.type.name === 'inline_math') {
        view.dispatch(view.state.tr.setNodeMarkup(mathEdit.pos, undefined, { tex: mathDraft }))
      }
    } else {
      try {
        view.dispatch(view.state.tr.replaceSelectionWith(schema.nodes.inline_math.create({ tex: mathDraft }), false))
      } catch (err) {
        console.error('cannot insert formula here — place cursor in text', err)
      }
    }
    setMathEdit(null)
    view.focus()
  }

  return (
    <div className="editor-wrap">
      <MainToolbar
        docPath={docPath}
        folderConnected={folderConnected}
        onConnectFolder={() => void connectFolder()}
        onInsertImage={(file) => void handleInsertImage(file)}
        onInsertFormula={() => {
          setMathDraft('')
          setMathEdit({ mode: 'insert' })
        }}
      />
      {uploadError && (
        <div className="app__banner app__banner--error" style={{ margin: '0 0 8px' }}>
          Image upload failed: {uploadError}
          <button type="button" onClick={() => setUploadError(null)}>
            Dismiss
          </button>
        </div>
      )}
      {tableActive && <TableToolbar viewRef={viewRef} onOpenOptions={openTableOptions} />}
      {tableOpts && (
        <TableOptionsModal
          draft={tableOpts}
          onChange={setTableOpts}
          onCancel={() => setTableOpts(null)}
          onApply={applyTableOptions}
        />
      )}
      <div className="editor-host" ref={hostRef} />

      {opaqueEdit && (
        <div className="opaque-modal__backdrop" onClick={() => setOpaqueEdit(null)}>
          <div className="opaque-modal" onClick={(e) => e.stopPropagation()}>
            <div className="opaque-modal__title">Edit source — {opaqueEdit.label}</div>
            {opaqueEdit.kind === 'math' && (
              <div style={{ padding: '0 16px' }}>
                <MathPreview tex={mathBodyFromDirective(draft)} displayMode />
                <LatexToolbar textareaRef={opaqueTextareaRef} value={draft} setValue={setDraft} />
              </div>
            )}
            {(opaqueEdit.kind === 'figure' || opaqueEdit.kind === 'image') && (
              <div style={{ padding: '0 16px' }}>
                <ImageReplaceControl
                  docPath={docPath}
                  raw={draft}
                  onReplace={(file) => void handleReplaceImage(file)}
                />
              </div>
            )}
            <textarea
              ref={opaqueTextareaRef}
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

      {mathEdit && (
        <div className="opaque-modal__backdrop" onClick={() => setMathEdit(null)}>
          <div className="opaque-modal" onClick={(e) => e.stopPropagation()}>
            <div className="opaque-modal__title">Edit formula</div>
            <div style={{ padding: '0 16px' }}>
              <MathPreview tex={mathDraft} displayMode />
              <LatexToolbar textareaRef={mathTextareaRef} value={mathDraft} setValue={setMathDraft} />
            </div>
            <textarea
              ref={mathTextareaRef}
              className="opaque-modal__textarea opaque-modal__textarea--math"
              value={mathDraft}
              onChange={(e) => setMathDraft(e.target.value)}
              spellCheck={false}
              placeholder="e.g. x^2 + y^2 = r^2"
            />
            <div className="opaque-modal__actions">
              <button type="button" onClick={() => setMathEdit(null)}>
                Cancel
              </button>
              <button type="button" className="primary" onClick={commitMathEdit}>
                Apply
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
