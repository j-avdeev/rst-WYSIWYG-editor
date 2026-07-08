// Minimal ambient types for the File System Access API surface this editor
// uses. Not yet part of TypeScript's lib.dom in this project's TS version.

export interface FileSystemPermissionDescriptor {
  mode?: 'read' | 'readwrite'
}

export interface FileSystemFileHandle {
  getFile(): Promise<File>
}

export interface FileSystemDirectoryHandle {
  readonly name: string
  getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<FileSystemDirectoryHandle>
  queryPermission(descriptor?: FileSystemPermissionDescriptor): Promise<PermissionState>
  requestPermission(descriptor?: FileSystemPermissionDescriptor): Promise<PermissionState>
}

declare global {
  interface Window {
    showOpenFilePicker?: (options?: {
      types?: { description?: string; accept: Record<string, string[]> }[]
      multiple?: boolean
      startIn?: FileSystemDirectoryHandle
    }) => Promise<FileSystemFileHandle[]>

    showDirectoryPicker?: (options?: { mode?: 'read' | 'readwrite' }) => Promise<FileSystemDirectoryHandle>
  }
}

export {}
