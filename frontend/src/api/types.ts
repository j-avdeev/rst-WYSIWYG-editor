export interface FileEntry {
  path: string
  name: string
  is_dir: boolean
  children: FileEntry[]
}

export interface EdNode {
  id: string
  type: string
  span: [number, number]
  raw_source: string
  attrs: Record<string, unknown>
  children: EdNode[]
  view: ViewNode | null
}

export interface EdDoc {
  path: string
  encoding: string
  bom: boolean
  eol: string
  nodes: EdNode[]
  warnings: string[]
  parse_errors: number
}

// The rendering-enrichment tree (rstkit/inline.py). Loosely typed — any
// unrecognized `type` at any level is treated as unsupported by the
// converter, which falls back to displaying the owning EdNode's raw_source.
export interface ViewNode {
  type: string
  text?: string
  href?: string
  name?: string
  raw?: string
  prefix?: string
  quoted?: boolean
  caption?: string
  directive?: string
  indent?: string
  delimiter?: string
  quote?: string
  options?: Array<Record<string, unknown>>
  header?: { raw?: string; cells?: ViewNode[] } | null
  rows?: Array<{ raw?: string; cells?: ViewNode[] }>
  cells?: ViewNode[]
  term?: ViewNode[]
  children?: ViewNode[]
}

export type SubstitutionKind = 'image' | 'replace'

export interface SubstitutionEntry {
  kind: SubstitutionKind
  uri?: string
  text?: string
}

export interface GetDocResponse {
  doc: EdDoc
  enriched: boolean
  size_bytes: number
  substitutions: Record<string, SubstitutionEntry>
  mtime_ns: number
}

export interface ProjectInfo {
  root: string
  name: string
}
