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
