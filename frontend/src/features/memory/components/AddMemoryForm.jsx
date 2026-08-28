'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { Check, X } from 'lucide-react'
import { toast } from 'sonner'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { CATEGORY_OPTIONS, MAX_CHARS } from './memoryConfig'

function AddMemoryForm({ onAdd, onCancel }) {
  const [content, setContent]   = useState('')
  const [category, setCategory] = useState('user_preference')
  const [loading, setLoading]   = useState(false)

  const handleSubmit = async () => {
    if (!content.trim()) { toast.error('Please enter memory content'); return }
    if (content.length > MAX_CHARS) { toast.error(`Max ${MAX_CHARS} characters`); return }
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
            className="flex h-7 w-7 items-center justify-center rounded-lg"
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
              className="w-full rounded-lg px-3 py-2.5 text-[15px] resize-none outline-hidden transition-all duration-150"
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
            <label className="label-xs block mb-1.5">Category</label>
            <div className="flex gap-1.5 flex-wrap">
              {CATEGORY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setCategory(opt.value)}
                  className="px-2.5 py-1 rounded-md text-[13px] font-medium transition-all duration-150 outline-hidden"
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
