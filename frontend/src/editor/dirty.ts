import type { Node } from 'prosemirror-model'
import type { EdDoc } from '../api/types'

// Wire format of PUT /api/doc and POST /api/preview (see backend assemble.py):
//   raw     — clean block, original raw_source emitted verbatim
//   rawedit — opaque card whose raw text was edited in the modal
//   node    — dirty rich block, serialized (+verified) by the backend
export type SaveBlock =
  | { op: 'raw'; raw: string }
  | { op: 'rawedit'; raw: string }
  | { op: 'node'; pm: unknown }

export class DirtyTracker {
  private originals = new Map<string, string>()
  private rawById = new Map<string, string>()
  private opaqueOriginalRaw = new Map<string, string>()

  /** Snapshot load-time state. Call with the PM doc actually shown (after
   * Node.fromJSON normalization) so later comparisons are apples-to-apples. */
  init(edDoc: EdDoc, pmDoc: Node): void {
    this.originals.clear()
    this.rawById.clear()
    this.opaqueOriginalRaw.clear()
    for (const n of edDoc.nodes) this.rawById.set(n.id, n.raw_source)
    pmDoc.forEach((child) => {
      const id = child.attrs.srcId as string | null
      if (id) {
        this.originals.set(id, JSON.stringify(child.toJSON()))
        if (child.type.name === 'opaque_block') {
          this.opaqueOriginalRaw.set(id, String(child.attrs.raw))
        }
      }
    })
  }

  isClean(child: Node): boolean {
    const id = child.attrs.srcId as string | null
    if (!id) return false
    return this.originals.get(id) === JSON.stringify(child.toJSON())
  }

  buildBlocks(pmDoc: Node): SaveBlock[] {
    const blocks: SaveBlock[] = []
    pmDoc.forEach((child) => {
      const id = child.attrs.srcId as string | null
      if (id && this.isClean(child)) {
        blocks.push({ op: 'raw', raw: this.rawById.get(id)! })
      } else if (child.type.name === 'opaque_block') {
        blocks.push({ op: 'rawedit', raw: String(child.attrs.raw) })
      } else {
        blocks.push({ op: 'node', pm: child.toJSON() })
      }
    })
    return blocks
  }

  dirtyCount(pmDoc: Node): number {
    let dirty = 0
    pmDoc.forEach((child) => {
      if (!this.isClean(child)) dirty += 1
    })
    return dirty
  }
}
