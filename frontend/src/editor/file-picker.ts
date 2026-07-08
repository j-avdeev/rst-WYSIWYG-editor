// A plain <input type="file"> always opens the OS dialog wherever the OS
// defaults to (often Downloads/Documents) — websites cannot control that.
// The File System Access API is different: Chromium remembers, *per origin*,
// the last folder a showOpenFilePicker() call was used in, and reopens there
// next time; passing `startIn` (see project-folder.ts) jumps straight to a
// specific granted folder instead of relying on that memory. Firefox/Safari
// don't support this API, so callers fall back to <input type="file">.
import './fs-access-types'
import type { FileSystemDirectoryHandle } from './fs-access-types'

const IMAGE_TYPES = [
  {
    description: 'Images',
    accept: {
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/gif': ['.gif'],
      'image/svg+xml': ['.svg'],
      'image/bmp': ['.bmp'],
      'image/webp': ['.webp'],
    },
  },
]

export type PickResult =
  | { status: 'picked'; file: File }
  | { status: 'cancelled' }
  | { status: 'unsupported' }

export function supportsFilePickerApi(): boolean {
  return typeof window !== 'undefined' && typeof window.showOpenFilePicker === 'function'
}

export async function pickImageFileViaFsAccess(
  startIn?: FileSystemDirectoryHandle,
): Promise<PickResult> {
  if (!window.showOpenFilePicker) return { status: 'unsupported' }
  try {
    const [handle] = await window.showOpenFilePicker({ types: IMAGE_TYPES, multiple: false, startIn })
    return { status: 'picked', file: await handle.getFile() }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return { status: 'cancelled' }
    return { status: 'unsupported' } // e.g. blocked by permissions policy — fall back to <input>
  }
}
