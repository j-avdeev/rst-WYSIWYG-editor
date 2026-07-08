import type { EdDoc, EdNode, SubstitutionEntry, ViewNode } from '../api/types'
import { assetUrl } from '../api/client'
import { schema } from './schema'

// Converts the backend's EdDoc (+ its best-effort `view` rendering trees)
// into ProseMirror JSON. Anything the converter doesn't recognize — at any
// level of nesting — makes the *owning top-level EdNode* fall back to an
// opaque_block showing its raw_source, rather than rendering a partial or
// silently-lossy tree. That fallback is what makes this safe to run on rst
// this editor doesn't fully understand yet.

type PMNode = { type: string; attrs?: Record<string, unknown>; content?: PMNode[]; marks?: PMMark[]; text?: string }
type PMMark = { type: string; attrs?: Record<string, unknown> }

class Unsupported extends Error {}

function convertInline(node: ViewNode, marks: PMMark[], docPath: string): PMNode[] {
  switch (node.type) {
    case 'text': {
      const text = node.text ?? ''
      if (!text) return []
      return [{ type: 'text', text, ...(marks.length ? { marks } : {}) }]
    }
    case 'strong':
      return flattenChildren(node, [...marks, { type: 'strong' }], docPath)
    case 'em':
      return flattenChildren(node, [...marks, { type: 'em' }], docPath)
    case 'literal':
      return flattenChildren(node, [...marks, { type: 'code' }], docPath)
    case 'superscript':
      return flattenChildren(node, [...marks, { type: 'sup' }], docPath)
    case 'subscript':
      return flattenChildren(node, [...marks, { type: 'sub' }], docPath)
    case 'title_ref':
      return flattenChildren(node, [...marks, { type: 'title_ref' }], docPath)
    case 'link':
      return flattenChildren(node, [...marks, { type: 'link', attrs: { href: node.href ?? '' } }], docPath)
    case 'math':
      return [{ type: 'inline_math', attrs: { tex: node.text ?? '' } }]
    case 'subst_ref':
      return [{ type: 'subst_ref', attrs: substRefAttrs(node.name ?? '', docPath) }]
    case 'opaque': {
      const text = node.text ?? ''
      if (!text) return []
      return [{ type: 'text', text, marks: [...marks, { type: 'opaque' }] }]
    }
    default:
      throw new Unsupported(`inline: ${node.type}`)
  }
}

function flattenChildren(node: ViewNode, marks: PMMark[], docPath: string): PMNode[] {
  return (node.children ?? []).flatMap((c) => convertInline(c, marks, docPath))
}

// filled in by the caller (Editor.tsx) before conversion, since substitution
// resolution needs the doc's own substitution index
let currentSubstitutions: Record<string, SubstitutionEntry> = {}

function substRefAttrs(name: string, docPath: string) {
  const entry = currentSubstitutions[name]
  if (entry?.kind === 'image' && entry.uri) {
    return { name, kind: 'image', src: assetUrl(docPath, entry.uri), text: '' }
  }
  if (entry?.kind === 'replace' && entry.text) {
    return { name, kind: 'replace', src: '', text: entry.text }
  }
  return { name, kind: '', src: '', text: '' }
}

function nonEmptyInline(content: PMNode[]): PMNode[] {
  // ProseMirror requires inline content nodes to be non-empty text; an
  // empty paragraph still needs `content: []` (not a stray empty text node).
  return content.filter((n) => n.type !== 'text' || n.text)
}

function convertBlock(view: ViewNode, docPath: string): PMNode {
  switch (view.type) {
    case 'paragraph':
      return { type: 'paragraph', content: nonEmptyInline(flattenChildren(view, [], docPath)) }
    case 'literal_block': {
      const text = view.text ?? ''
      return { type: 'literal_block', content: text ? [{ type: 'text', text }] : [] }
    }
    case 'block_quote': {
      const content = (view.children ?? []).map((c) => convertBlock(c, docPath))
      if (!content.length) throw new Unsupported('empty block_quote')
      return { type: 'blockquote', content }
    }
    case 'bullet_list':
    case 'enumerated_list': {
      const listType = view.type === 'bullet_list' ? 'bullet_list' : 'ordered_list'
      const items = (view.children ?? []).map((item) => {
        const content = (item.children ?? []).map((c) => convertBlock(c, docPath))
        if (!content.length) throw new Unsupported('empty list_item')
        return { type: 'list_item', content }
      })
      if (!items.length) throw new Unsupported('empty list')
      return { type: listType, content: items }
    }
    case 'block_group': {
      const content = (view.children ?? []).map((c) => convertBlock(c, docPath))
      if (!content.length) throw new Unsupported('empty block_group')
      return { type: 'block_group', content }
    }
    default:
      throw new Unsupported(`block: ${view.type}`)
  }
}

function opaqueFallback(node: EdNode): PMNode {
  return {
    type: 'opaque_block',
    attrs: {
      raw: node.raw_source,
      kind: String(node.attrs.name ?? node.type),
      label: node.type === 'directive' ? `.. ${node.attrs.name ?? ''}::` : node.type,
      srcId: node.id,
    },
  }
}

// A structurally-plausible PMNode JSON can still violate schema content
// rules (e.g. a list_item whose first child isn't a paragraph) — those only
// surface when ProseMirror actually validates the node tree. Check that
// here, per top-level node, so one bad fragment can't take down the whole
// document render.
function validated(candidate: PMNode, node: EdNode): PMNode {
  try {
    schema.nodeFromJSON(candidate)
    return candidate
  } catch {
    return opaqueFallback(node)
  }
}

function withSrcId(pm: PMNode, id: string): PMNode {
  return { ...pm, attrs: { ...(pm.attrs ?? {}), srcId: id } }
}

function convertTopLevel(node: EdNode, docPath: string): PMNode {
  if (node.type === 'heading') {
    const title = String(node.attrs.title ?? '')
    const level = Number(node.attrs.level ?? 1)
    let content: PMNode[] = title ? [{ type: 'text', text: title }] : []
    if (node.view && node.view.type === 'heading_title') {
      try {
        content = nonEmptyInline(flattenChildren(node.view, [], docPath))
      } catch {
        // keep the plain-title fallback computed above
      }
    }
    return validated(
      withSrcId(
        {
          type: 'heading',
          attrs: { level, underline: node.attrs.underline ?? '=', overline: !!node.attrs.overline },
          content,
        },
        node.id,
      ),
      node,
    )
  }

  if (node.type === 'text' && node.view) {
    try {
      return validated(withSrcId(convertBlock(node.view, docPath), node.id), node)
    } catch {
      // fall through to opaque fallback below
    }
  }

  return opaqueFallback(node)
}

// Section depth (heading level) by first-seen-adornment-char convention.
function assignHeadingLevels(nodes: EdNode[]): void {
  const levelOf = new Map<string, number>()
  for (const node of nodes) {
    if (node.type !== 'heading') continue
    const key = `${node.attrs.underline}${node.attrs.overline ? ':over' : ''}`
    if (!levelOf.has(key)) levelOf.set(key, levelOf.size + 1)
    node.attrs.level = Math.min(levelOf.get(key)!, 6)
  }
}

export function edDocToPMDoc(doc: EdDoc, substitutions: Record<string, SubstitutionEntry>): PMNode {
  currentSubstitutions = substitutions
  assignHeadingLevels(doc.nodes)
  const content = doc.nodes
    .filter((n) => n.raw_source.trim().length > 0 || n.type === 'heading')
    .map((n) => convertTopLevel(n, doc.path))
  return { type: 'doc', content: content.length ? content : [{ type: 'paragraph', content: [] }] }
}
