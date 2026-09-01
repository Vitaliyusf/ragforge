'use client'

import { useState } from 'react'
import { FileText } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { groupSourcesByDocument } from '@/features/chat/utils/answerSources'
import { useI18n } from '@/i18n'

/**
 * The documents an answer was built from, as compact chips.
 *
 * A chip names a document, not a chunk: several retrieved passages from the
 * same file read as one source to a person. Opening a chip shows only what a
 * reader can use — the page and the passage text — so scores, chunk indexes
 * and chunk IDs stay in the Developer Inspector where they belong. A chip with
 * nothing readable behind it is not clickable at all, so the affordance never
 * promises detail the turn does not carry.
 *
 * The grouping itself lives in `utils/answerSources`, shared with the quality
 * line above so both surfaces count the same thing.
 */

const MAX_VISIBLE = 4

export default function AnswerSources({ sources }) {
  const { t } = useI18n()
  const [openName, setOpenName] = useState(null)
  const [showAll, setShowAll] = useState(false)

  if (!Array.isArray(sources) || sources.length === 0) return null

  const groups = groupSourcesByDocument(sources)
  const visible = showAll ? groups : groups.slice(0, MAX_VISIBLE)
  const overflow = groups.length - visible.length
  const open = groups.find((group) => group.name === openName && group.passages.length) || null

  return (
    <div className="mt-3">
      <div className="flex w-full flex-wrap items-center gap-1.5">
        {/* A labelled count, not a plural: the same phrasing has to read
            correctly in Hebrew, where "1 source" has no clean equivalent. */}
        <span className="text-xs text-[var(--fg-soft)]">
          {t('chat.sourceCount', { count: groups.length })}
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
            {t('chat.moreSources', { count: overflow })}
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
                  {/* The word is copy and follows the interface locale; the
                      number beside it is an ordinary count and needs no
                      isolation once the label carries the direction. */}
                  {passage.page != null ? (
                    <div className="mb-0.5 text-xs text-[var(--fg-soft)]">
                      {t('chat.page', { page: passage.page })}
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
