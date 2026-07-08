import { useMemo, useState } from 'react'
import { GitPanel } from './GitPanel'
import './RightPanel.css'

export interface PreviewData {
  html: string
  text: string
  blocks: { text: string; dirty: boolean; error?: string | null }[]
}

const PREVIEW_CSS = `
  body { font-family: -apple-system, Segoe UI, sans-serif; font-size: 14px;
         line-height: 1.55; color: #1a1a1a; margin: 16px 20px; }
  h1,h2,h3,h4 { font-weight: 600; border-bottom: 1px solid #e5e5e5; padding-bottom: .2em; }
  table { border-collapse: collapse; font-size: 0.92em; }
  table, th, td { border: 1px solid #cbd5e1; }
  th, td { padding: 4px 8px; vertical-align: top; }
  th { background: #f1f5f9; }
  pre, .literal-block { background: #f5f5f5; border: 1px solid #e0e0e0;
        border-radius: 4px; padding: 8px 10px; overflow-x: auto;
        font-family: Consolas, monospace; font-size: .9em; }
  code, .docutils.literal { background: #f0f0f0; padding: .1em .3em;
        border-radius: 3px; font-family: Consolas, monospace; font-size: .9em; }
  img { max-width: 100%; }
  a { color: #2563eb; }
  .preview-error { background: #fef2f2; color: #b91c1c; padding: 8px 10px;
        border-radius: 4px; }
  .system-message { display: none; }
`

export function RightPanel({
  data,
  loading,
  gitRefreshKey,
  onWorkingTreeChanged,
}: {
  data: PreviewData | null
  loading: boolean
  gitRefreshKey: number
  onWorkingTreeChanged: (path: string) => void
}) {
  const [tab, setTab] = useState<'preview' | 'source' | 'git'>('preview')

  const srcdoc = useMemo(
    () => (data ? `<!doctype html><meta charset="utf-8"><style>${PREVIEW_CSS}</style>${data.html}` : ''),
    [data],
  )

  return (
    <div className="right-panel">
      <div className="right-panel__tabs">
        <button
          type="button"
          className={tab === 'preview' ? 'active' : ''}
          onClick={() => setTab('preview')}
        >
          Preview
        </button>
        <button
          type="button"
          className={tab === 'source' ? 'active' : ''}
          onClick={() => setTab('source')}
        >
          Source
        </button>
        <button type="button" className={tab === 'git' ? 'active' : ''} onClick={() => setTab('git')}>
          Git
        </button>
        {loading && <span className="right-panel__spinner">…</span>}
      </div>
      {tab === 'preview' && (
        <iframe className="right-panel__preview" sandbox="" srcDoc={srcdoc} title="preview" />
      )}
      {tab === 'source' && (
        <div className="right-panel__source">
          {data?.blocks.map((b, i) => (
            <pre key={i} className={b.dirty ? 'src-block src-block--dirty' : 'src-block'}>
              {b.text}
            </pre>
          ))}
        </div>
      )}
      {tab === 'git' && (
        <GitPanel refreshKey={gitRefreshKey} onWorkingTreeChanged={onWorkingTreeChanged} />
      )}
    </div>
  )
}
