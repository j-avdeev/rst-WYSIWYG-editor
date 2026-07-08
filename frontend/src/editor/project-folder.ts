// One-time "connect your docs folder" flow: the user grants access to the
// Sphinx source directory once via showDirectoryPicker(); we persist the
// FileSystemDirectoryHandle in IndexedDB (handles are structured-cloneable)
// so every later image picker can resolve straight to the *correct* page's
// media/ folder as `startIn`, with no per-page navigation ever required.
import './fs-access-types'
import type { FileSystemDirectoryHandle } from './fs-access-types'

const DB_NAME = 'rst-editor'
const STORE = 'handles'
const ROOT_KEY = 'projectRoot'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function saveRootHandle(handle: FileSystemDirectoryHandle): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put(handle, ROOT_KEY)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function loadRootHandle(): Promise<FileSystemDirectoryHandle | null> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const req = tx.objectStore(STORE).get(ROOT_KEY)
    req.onsuccess = () => resolve((req.result as FileSystemDirectoryHandle) ?? null)
    req.onerror = () => reject(req.error)
  })
}

export function supportsFolderAccess(): boolean {
  return typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function'
}

/** IndexedDB check only, no permission prompt — safe to call outside a user
 * gesture (e.g. on mount) to decide whether to show a "connect" affordance. */
export async function hasStoredProjectFolder(): Promise<boolean> {
  if (!supportsFolderAccess()) return false
  try {
    return (await loadRootHandle()) !== null
  } catch {
    return false
  }
}

/** Must be called from within a user gesture (button click). */
export async function requestProjectFolderAccess(): Promise<boolean> {
  if (!window.showDirectoryPicker) return false
  try {
    const handle = await window.showDirectoryPicker({ mode: 'readwrite' })
    await saveRootHandle(handle)
    return true
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return false
    console.error('failed to save project folder handle', err)
    return false
  }
}

/** Re-affirms permission if needed (also requires a user gesture the first
 * time in a given browser session) and returns the handle, or null if it's
 * never been granted / was revoked / the user declines re-confirmation. */
async function getVerifiedRootHandle(): Promise<FileSystemDirectoryHandle | null> {
  if (!supportsFolderAccess()) return null
  let handle: FileSystemDirectoryHandle | null
  try {
    handle = await loadRootHandle()
  } catch {
    return null
  }
  if (!handle) return null
  try {
    const current = await handle.queryPermission({ mode: 'readwrite' })
    if (current === 'granted') return handle
    const granted = await handle.requestPermission({ mode: 'readwrite' })
    return granted === 'granted' ? handle : null
  } catch {
    return null
  }
}

/** Walks from the granted root down to `<docDir>/media/`, creating the
 * media/ subfolder if this page doesn't have one yet. Returns null on any
 * mismatch (e.g. the user granted a different folder than the docs root) —
 * callers treat that as "no hint available" and fall back gracefully. */
async function resolveMediaDir(
  root: FileSystemDirectoryHandle,
  docRelPath: string,
): Promise<FileSystemDirectoryHandle | null> {
  const segments = docRelPath.split('/').slice(0, -1)
  try {
    let dir = root
    for (const seg of segments) {
      dir = await dir.getDirectoryHandle(seg, { create: false })
    }
    return await dir.getDirectoryHandle('media', { create: true })
  } catch {
    return null
  }
}

/** Best-effort `startIn` hint for a file picker: the granted-and-verified
 * media/ directory for this specific document, or undefined if folder
 * access was never granted, permission lapsed, or resolution failed for
 * any reason — callers pass this straight through to showOpenFilePicker,
 * where `undefined` just means "use the browser's own last-used folder." */
export async function getMediaDirHint(
  docRelPath: string,
): Promise<FileSystemDirectoryHandle | undefined> {
  const root = await getVerifiedRootHandle()
  if (!root) return undefined
  const media = await resolveMediaDir(root, docRelPath)
  return media ?? undefined
}
