'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import { notifyError } from '@/lib/notify'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { CATEGORY_OPTIONS, MAX_CHARS } from './memoryConfig'

/** Every control below suppresses the UA outline for the app ring, so the
    ring is spelled out rather than left to the browser default. */
const FOCUS_RING =
  'focus:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface)]'

function AddMemoryForm({ onAdd, onCancel }) {
  const [content, setContent]   = useState('')
  const [category, setCategory] = useState('user_preference')
  const [loading, setLoading]   = useState(false)

  // Roving focus for the category radiogroup: the group is one tab stop and
  // the arrow keys move (and select) inside it, which is what a screen reader
  // promises the moment the options are announced as radios.
  const handleCategoryKeyDown = (event) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const index = CATEGORY_OPTIONS.findIndex(opt => opt.value === category)
    const next = CATEGORY_OPTIONS[(index + step + CATEGORY_OPTIONS.length) % CATEGORY_OPTIONS.length]
    setCategory(next.value)
    event.currentTarget.parentElement
      ?.querySelector(`[data-category="${next.value}"]`)
      ?.focus()
  }

  const handleSubmit = async () => {
    if (!content.trim()) { notifyError('Please enter memory content'); return }
    if (content.length > MAX_CHARS) { notifyError(`Max ${MAX_CHARS} characters`); return }
    setLoading(true)
    try {
      await onAdd(content.trim(), category)
      setContent(''); setCategory('user_preference')
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="overflow-hidden"
    >
      <div
        className="rounded-xl p-4 mb-4"
        style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between mb-3">
          <span className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>New Memory</span>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Cancel adding memory"
            className={cn('flex h-7 w-7 items-center justify-center rounded-lg', FOCUS_RING)}
            style={{ color: 'var(--fg-soft)' }}
          >
            <X size={14} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="Enter memory content…"
              maxLength={MAX_CHARS}
              rows={3}
              aria-label="Memory content"
              className={cn(
                'w-full rounded-lg px-3 py-2.5 text-[15px] resize-none transition-colors duration-150',
                FOCUS_RING
              )}
              style={{
                background:  'var(--surface)',
                border:      `1px solid ${content.length > MAX_CHARS * 0.9 ? 'var(--warning)' : 'var(--border)'}`,
                color:       'var(--fg)',
              }}
              onFocus={e => e.currentTarget.style.borderColor = 'var(--border-focus)'}
              onBlur={e => e.currentTarget.style.borderColor = content.length > MAX_CHARS * 0.9 ? 'var(--warning)' : 'var(--border)'}
            />
            <div className="flex justify-end mt-1">
              <span
                className="text-xs font-mono"
                style={{ color: content.length > MAX_CHARS ? 'var(--danger)' : 'var(--fg-soft)' }}
              >
                {content.length}/{MAX_CHARS}
              </span>
            </div>
          </div>

          <div>
            <span className="label-xs block mb-1.5" id="memory-category-label">Category</span>
            {/* One choice out of a fixed set: a radiogroup, so a screen reader
                announces the selection and arrow keys move between options
                instead of Tab walking every category. */}
            <div
              className="flex gap-1.5 flex-wrap"
              role="radiogroup"
              aria-labelledby="memory-category-label"
            >
              {CATEGORY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  data-category={opt.value}
                  onKeyDown={handleCategoryKeyDown}
                  aria-checked={category === opt.value}
                  tabIndex={category === opt.value ? 0 : -1}
                  onClick={() => setCategory(opt.value)}
                  className={cn(
                    'px-2.5 py-1 rounded-md text-[13px] font-medium transition-colors duration-150',
                    FOCUS_RING
                  )}
                  style={{
                    background:  category === opt.value ? 'var(--primary-soft)' : 'var(--surface-hover)',
                    color:       category === opt.value ? 'var(--primary)' : 'var(--fg-muted)',
                    border:      `1px solid ${category === opt.value ? 'var(--border-focus)' : 'transparent'}`,
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-2 justify-end pt-1">
            <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
            <Button variant="primary" size="sm" loading={loading} onClick={handleSubmit}>
              Save Memory
            </Button>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

export default AddMemoryForm
