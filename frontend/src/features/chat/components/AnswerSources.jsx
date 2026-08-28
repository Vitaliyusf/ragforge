'use client'

import { useState } from 'react'
import { FileText } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'

/**
 * The documents an answer was built from, as compact chips.
 *
 * A chip names a document, not a chunk: several retrieved passages from the
 * same file read as one source to a person. Opening a chip shows only what a
 * reader can use — the page and the passage text — so scores, chunk indexes
 * and chunk IDs stay in the Developer Inspector where they belong. A chip with
 * nothing readable behind it is not clickable at all, so the affordance never
 * promises detail the turn does not carry.
 */

const MAX_VISIBLE = 4

function sourceName(source, index) {
  return source?.source_name || source?.source || source?.filename || source?.title || `Source ${index + 1}`
}

function excerptOf(source) {
  const text = source?.text_preview || source?.text
  return typeof text === 'string' && text.trim() ? text.trim() : null
}

/** Group retrieved passages by the document they came from, preserving order. */
function groupSources(sources) {
  const groups = []
  const byName = new Map()

  for (const [index, source] of sources.entries()) {
    const name = sourceName(source, index)
    let group = byName.get(name)
    if (!group) {
      group = { name, passages: [] }
      byName.set(name, group)
      groups.push(group)
    }
    const excerpt = excerptOf(source)
    const page = source?.page ?? null
    if (excerpt || page != null) group.passages.push({ page, excerpt })
  }

  return groups
}

export default function AnswerSources({ sources }) {
  const [openName, setOpenName] = useState(null)
  const [showAll, setShowAll] = useState(false)

  if (!Array.isArray(sources) || sources.length === 0) return null

  const groups = groupSources(sources)
  const visible = showAll ? groups : groups.slice(0, MAX_VISIBLE)
  const overflow = groups.length - visible.length
  const open = groups.find((group) => group.name === openName && group.passages.length) || null

  return (
    <div className="mt-3">
      <div className="flex w-full flex-wrap items-center gap-1.5">
        <span className="text-xs text-[var(--fg-soft)]">
          {groups.length === 1 ? '1 source' : `${groups.length} sources`}
        </span>
        {visible.map((group) => {
          const inspectable = group.passages.length > 0
          const isOpen = openName === group.name
          const chipClass =
            'inline-flex max-w-[15rem] items-center gap-1 truncate rounded-lg border px-2 py-1 text-xs text-[var(--fg-muted)]'
          const chipStyle = {
            borderColor: isOpen ? 'var(--primary)' : 'var(--border)',
            background: isOpen ? 'var(--primary-soft)' : 'var(--surface-hover)',
          }
          const body = (
            <>
              <FileText size={11} className="shrink-0" aria-hidden="true" />
              <span className="truncate">{group.name}</span>
            </>
          )

          return inspectable ? (
            <button
              key={group.name}
              type="button"
              dir="auto"
              title={group.name}
              aria-expanded={isOpen}
              onClick={() => setOpenName(isOpen ? null : group.name)}
              className={`${chipClass} transition-colors hover:border-[var(--primary)] focus-visible:outline-hidden focus-visible:ring-2`}
              style={chipStyle}
            >
              {body}
            </button>
          ) : (
            <span key={group.name} dir="auto" title={group.name} className={chipClass} style={chipStyle}>
              {body}
            </span>
          )
        })}
        {overflow > 0 ? (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="rounded-lg px-1 py-1 text-xs text-[var(--fg-soft)] underline underline-offset-2 transition-colors hover:text-[var(--fg)]"
          >
            +{overflow} more
          </button>
        ) : null}
      </div>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key={open.name}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div
              className="mt-2 space-y-2 rounded-xl border p-3"
              style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
            >
              {open.passages.map((passage, index) => (
                <div key={index}>
                  {passage.page != null ? (
                    <div dir="ltr" className="mb-0.5 text-xs text-[var(--fg-soft)] [unicode-bidi:isolate]">
                      Page {passage.page}
                    </div>
                  ) : null}
                  {passage.excerpt ? (
                    <p dir="auto" className="line-clamp-4 text-[13px] leading-relaxed text-[var(--fg-muted)]">
                      {passage.excerpt}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
