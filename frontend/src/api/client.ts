import type { FileEntry, GetDocResponse, ProjectInfo } from './types'

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export function getProject(): Promise<ProjectInfo> {
  return getJson('/api/project')
}

export function getFileTree(): Promise<FileEntry> {
  return getJson('/api/files')
}

export function getDoc(relPath: string): Promise<GetDocResponse> {
  return getJson(`/api/doc/${encodePath(relPath)}`)
}

function encodePath(relPath: string): string {
  return relPath.split('/').map(encodeURIComponent).join('/')
}

export class HttpError extends Error {
  status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function jsonOrError<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* keep the status line */
    }
    throw new HttpError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export async function saveDoc(
  relPath: string,
  baseMtimeNs: number,
  blocks: unknown[],
): Promise<GetDocResponse> {
  const res = await fetch(`/api/doc/${encodePath(relPath)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_mtime_ns: baseMtimeNs, blocks }),
  })
  return jsonOrError<GetDocResponse>(res)
}

export async function fetchPreview(
  relPath: string,
  blocks: unknown[],
): Promise<{ html: string; text: string; blocks: { text: string; dirty: boolean; error?: string | null }[] }> {
  const res = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: relPath, blocks }),
  })
  return jsonOrError(res)
}

export function assetUrl(docPath: string, uri: string): string {
  const params = new URLSearchParams({ doc: docPath, uri })
  return `/api/asset?${params.toString()}`
}

export async function uploadAsset(docPath: string, file: File): Promise<{ uri: string }> {
  const form = new FormData()
  form.append('doc', docPath)
  form.append('file', file)
  const res = await fetch('/api/asset', { method: 'POST', body: form })
  return jsonOrError(res)
}

export type ImageOp = 'rotate90' | 'flip_h' | 'flip_v' | 'crop'

export interface CropRect {
  x: number
  y: number
  width: number
  height: number
}

export async function transformAsset(
  docPath: string,
  uri: string,
  op: ImageOp,
  crop?: CropRect,
): Promise<{ uri: string }> {
  const res = await fetch('/api/asset/transform', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc: docPath, uri, op, crop: crop ?? null }),
  })
  return jsonOrError(res)
}

// --- git ------------------------------------------------------------------

export interface GitFileStatus {
  path: string
  status: string
}

export interface GitStatusResponse {
  branch: string
  files: GitFileStatus[]
}

export async function gitStatus(): Promise<GitStatusResponse> {
  return jsonOrError(await fetch('/api/git/status'))
}

export async function gitDiff(path: string): Promise<{ path: string; untracked: boolean; diff: string }> {
  return jsonOrError(await fetch(`/api/git/diff?${new URLSearchParams({ path })}`))
}

export async function gitCommit(message: string, paths: string[]): Promise<{ head: string }> {
  const res = await fetch('/api/git/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, paths }),
  })
  return jsonOrError(res)
}

export async function gitDiscard(path: string): Promise<void> {
  const res = await fetch('/api/git/discard', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  await jsonOrError(res)
}

// --- sphinx build ------------------------------------------------------------

export interface BuildStatus {
  state: 'idle' | 'running' | 'succeeded' | 'failed'
  elapsed_sec: number | null
  warnings: number
  log_tail: string[]
}

export async function startBuild(): Promise<BuildStatus> {
  return jsonOrError(await fetch('/api/build', { method: 'POST' }))
}

export async function buildStatus(): Promise<BuildStatus> {
  return jsonOrError(await fetch('/api/build/status'))
}

export function builtUrlFor(docPath: string): string {
  const docname = docPath.replace(/\.rst$/i, '')
  return `/built/${docname}.html`
}

// --- table of contents --------------------------------------------------------

export interface TocEntrySource {
  file: string
  toctree_index: number
  position: number
}

export interface TocNode {
  docname: string
  path: string
  title: string
  missing?: boolean
  source: TocEntrySource | null
  children: TocNode[]
}

export interface TocResponse {
  master: string
  tree: TocNode
  orphans: { docname: string; path: string; title: string }[]
}

export async function getToc(): Promise<TocResponse> {
  return jsonOrError(await fetch('/api/toc'))
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return jsonOrError(res)
}

export function tocReorder(file: string, toctreeIndex: number, fromPos: number, toPos: number): Promise<TocResponse> {
  return postJson('/api/toc/reorder', { file, toctree_index: toctreeIndex, from_pos: fromPos, to_pos: toPos })
}

export function tocRemove(file: string, toctreeIndex: number, position: number): Promise<TocResponse> {
  return postJson('/api/toc/remove', { file, toctree_index: toctreeIndex, position })
}

export function tocAddEntry(indexFile: string, docPath: string): Promise<TocResponse> {
  return postJson('/api/toc/entry', { index_file: indexFile, doc_path: docPath })
}

// --- file management --------------------------------------------------------

export async function createPage(
  path: string,
  title: string,
  toctreeIndex: string | null,
): Promise<{ path: string; toctree_updated: boolean }> {
  const res = await fetch('/api/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, title, toctree_index: toctreeIndex }),
  })
  return jsonOrError(res)
}

export async function importDocument(
  path: string,
  file: File,
  toctreeIndex: string | null,
): Promise<{ path: string; toctree_updated: boolean; parse_errors: number }> {
  const form = new FormData()
  form.append('path', path)
  if (toctreeIndex) form.append('toctree_index', toctreeIndex)
  form.append('file', file)
  const res = await fetch('/api/import', { method: 'POST', body: form })
  return jsonOrError(res)
}

export async function renamePage(
  path: string,
  newPath: string,
): Promise<{ path: string; toctrees_updated: string[] }> {
  const res = await fetch('/api/files/rename', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, new_path: newPath }),
  })
  return jsonOrError(res)
}
