import { Schema } from 'prosemirror-model'
import type { NodeSpec, MarkSpec } from 'prosemirror-model'
import OrderedMap from 'orderedmap'
import { addListNodes } from 'prosemirror-schema-list'
import { tableNodes } from 'prosemirror-tables'

// Phase 1 whitelist v1: sections/paragraphs/lists + inline basics, plus the
// opaque-block/opaque-mark escape hatch for everything else. Editing (Phase
// 2+) reuses this same schema — Phase 1 just runs the EditorView read-only.

// srcId links a top-level PM node back to the EdNode it came from; blocks
// whose current JSON still equals their load-time JSON are sent back as the
// original raw_source on save (byte-exact). Nested copies of these nodes just
// carry a null srcId.
const srcId = { default: null as string | null }

const baseNodes: Record<string, NodeSpec> = {
  doc: { content: 'block+' },

  paragraph: {
    content: 'inline*',
    group: 'block',
    attrs: { srcId },
    parseDOM: [{ tag: 'p' }],
    toDOM: () => ['p', 0],
  },

  heading: {
    content: 'inline*',
    group: 'block',
    attrs: { level: { default: 1 }, underline: { default: '=' }, overline: { default: false }, srcId },
    parseDOM: [1, 2, 3, 4, 5, 6].map((level) => ({ tag: `h${level}`, attrs: { level } })),
    toDOM: (node) => [`h${Math.min(node.attrs.level, 6)}`, { 'data-underline': node.attrs.underline }, 0],
  },

  blockquote: {
    content: 'block+',
    group: 'block',
    attrs: { srcId },
    parseDOM: [{ tag: 'blockquote' }],
    toDOM: () => ['blockquote', 0],
  },

  // Adjacent blocks glued by indentation in the source (e.g. "intro::" +
  // literal block). Transparent container — NOT a quote; the backend
  // serializer reconstructs the :: linkage.
  block_group: {
    content: 'block+',
    group: 'block',
    attrs: { srcId },
    parseDOM: [{ tag: 'div.block-group' }],
    toDOM: () => ['div', { class: 'block-group' }, 0],
  },

  literal_block: {
    content: 'text*',
    group: 'block',
    code: true,
    whitespace: 'pre',
    marks: '',
    attrs: { srcId },
    parseDOM: [{ tag: 'pre' }],
    toDOM: () => ['pre', ['code', 0]],
  },

  // A whole unwhitelisted rst construct (directive, comment, transition, or
  // any "text" block the isolated-parse enrichment couldn't map). Shows the
  // exact raw_source; never editable inline, matching the plan's "source
  // card" design. attrs.directiveName is shown as a badge in the NodeView.
  opaque_block: {
    group: 'block',
    atom: true,
    isolating: true,
    attrs: { raw: { default: '' }, kind: { default: '' }, label: { default: '' }, srcId },
    parseDOM: [{ tag: 'div.opaque-block' }],
    toDOM: (node) => [
      'div',
      { class: 'opaque-block' },
      ['div', { class: 'opaque-block__label' }, node.attrs.label || node.attrs.kind],
      ['pre', node.attrs.raw],
    ],
  },

  // Inline atoms
  inline_math: {
    group: 'inline',
    inline: true,
    atom: true,
    attrs: { tex: { default: '' } },
    toDOM: (node) => ['span', { class: 'inline-math', title: node.attrs.tex }, `:math:\`${node.attrs.tex}\``],
  },

  subst_ref: {
    group: 'inline',
    inline: true,
    atom: true,
    attrs: { name: { default: '' }, kind: { default: '' }, src: { default: '' }, text: { default: '' } },
    toDOM: (node) => {
      if (node.attrs.kind === 'image' && node.attrs.src) {
        return ['img', { class: 'subst-ref subst-ref--image', src: node.attrs.src, alt: node.attrs.name, title: `|${node.attrs.name}|` }]
      }
      return ['span', { class: 'subst-ref subst-ref--chip', title: `|${node.attrs.name}|` }, node.attrs.text || `|${node.attrs.name}|`]
    },
  },

  text: { group: 'inline' },
}

const marks: Record<string, MarkSpec> = {
  strong: {
    parseDOM: [{ tag: 'strong' }],
    toDOM: () => ['strong', 0],
  },
  em: {
    parseDOM: [{ tag: 'em' }],
    toDOM: () => ['em', 0],
  },
  code: {
    parseDOM: [{ tag: 'code' }],
    toDOM: () => ['code', 0],
  },
  link: {
    attrs: { href: { default: '' } },
    parseDOM: [{ tag: 'a[href]' }],
    toDOM: (mark) => ['a', { href: mark.attrs.href, target: '_blank', rel: 'noreferrer' }, 0],
  },
  sup: { parseDOM: [{ tag: 'sup' }], toDOM: () => ['sup', 0] },
  sub: { parseDOM: [{ tag: 'sub' }], toDOM: () => ['sub', 0] },
  title_ref: { parseDOM: [{ tag: 'cite' }], toDOM: () => ['cite', 0] },
  opaque: {
    // unrecognized inline role/markup, kept as plain (but visually marked) text
    toDOM: () => ['span', { class: 'inline-opaque' }, 0],
  },
}

let nodesWithLists = addListNodes(OrderedMap.from(baseNodes), 'paragraph block*', 'block')

// lists can be top-level blocks too, so they also need srcId
for (const name of ['bullet_list', 'ordered_list'] as const) {
  const spec = nodesWithLists.get(name)!
  nodesWithLists = nodesWithLists.update(name, {
    ...spec,
    attrs: { ...(spec.attrs ?? {}), srcId },
  })
}

const csvCellAttr = {
  default: null,
  getFromDOM: () => null,
  setDOMAttr: () => {},
}

let nodesWithTables = nodesWithLists.append(
  OrderedMap.from(
    tableNodes({
      tableGroup: 'block',
      cellContent: 'paragraph+',
      cellAttributes: {
        csvRaw: csvCellAttr,
        csvPrefix: csvCellAttr,
        csvQuoted: csvCellAttr,
        csvInitialContent: csvCellAttr,
      },
    }),
  ),
)

const tableSpec = nodesWithTables.get('table')!
nodesWithTables = nodesWithTables.update('table', {
  ...tableSpec,
  attrs: { ...(tableSpec.attrs ?? {}), srcId, csv: { default: null } },
  toDOM: (node) => {
    const csv = node.attrs.csv as { caption?: string } | null
    const attrs = { class: csv ? 'rst-csv-table' : '' }
    if (csv?.caption) return ['table', attrs, ['caption', csv.caption], ['tbody', 0]]
    return ['table', attrs, ['tbody', 0]]
  },
})

const rowSpec = nodesWithTables.get('table_row')!
nodesWithTables = nodesWithTables.update('table_row', {
  ...rowSpec,
  attrs: { ...(rowSpec.attrs ?? {}), csvRaw: { default: null }, csvCellCount: { default: null } },
})

export const schema = new Schema({
  nodes: nodesWithTables,
  marks,
})
