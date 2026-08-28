'use client'

import { FileText } from 'lucide-react'

/**
 * The passages an answer was built from, as compact chips.
 *
 * Source names are user content and may be Hebrew, so they get `dir="auto"`;
 * the chunk/page markers beside them are technical and stay left-to-right.
 */

const MAX_VISIBLE = 4

function sourceName(source, index) {
  return source?.source_name || source?.source || source?.filename || source?.title || `Source ${index + 1}`
}

export default function AnswerSources({ sources }) {
  if (!Array.isArray(sources) || sources.length === 0) return null

  // One chip per document: several retrieved chunks from the same file read as
  // one source to a person.
  const names = []
  for (const [index, source] of sources.entries()) {
    const name = sourceName(source, index)
    if (!names.includes(name)) names.push(name)
  }

  const visible = names.slice(0, MAX_VISIBLE)
  const overflow = names.length - visible.length

  return (
    <div className="mt-2 flex w-full flex-wrap items-center gap-1.5">
      <span className="text-xs text-[var(--fg-soft)]">Sources</span>
      {visible.map((name) => (
        <span
          key={name}
          dir="auto"
          title={name}
          className="inline-flex max-w-[15rem] items-center gap-1 truncate rounded-lg border px-2 py-1 text-xs text-[var(--fg-muted)]"
          style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
        >
          <FileText size={11} className="shrink-0" aria-hidden="true" />
          <span className="truncate">{name}</span>
        </span>
      ))}
      {overflow > 0 ? (
        <span className="text-xs text-[var(--fg-soft)]">+{overflow} more</span>
      ) : null}
    </div>
  )
}
