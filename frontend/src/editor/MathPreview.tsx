import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

export function MathPreview({ tex, displayMode = false }: { tex: string; displayMode?: boolean }) {
  const { html, error } = useMemo(() => {
    if (!tex.trim()) return { html: '', error: null as string | null }
    try {
      return { html: katex.renderToString(tex, { throwOnError: true, displayMode }), error: null }
    } catch (err) {
      return { html: '', error: err instanceof Error ? err.message : String(err) }
    }
  }, [tex, displayMode])

  if (error) {
    return <div className="math-preview math-preview--error">Invalid LaTeX: {error}</div>
  }
  if (!html) {
    return <div className="math-preview math-preview--empty">Formula preview appears here</div>
  }
  // eslint-disable-next-line react/no-danger -- katex output is not user-navigable HTML
  return <div className="math-preview" dangerouslySetInnerHTML={{ __html: html }} />
}
