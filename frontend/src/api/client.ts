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
  return getJson(`/api/doc/${relPath.split('/').map(encodeURIComponent).join('/')}`)
}

export function assetUrl(docPath: string, uri: string): string {
  const params = new URLSearchParams({ doc: docPath, uri })
  return `/api/asset?${params.toString()}`
}
