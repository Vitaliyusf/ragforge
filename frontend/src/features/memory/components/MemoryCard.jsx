'use client'

import { memo, useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, Check, ChevronDown, ChevronUp, Edit2, Lock, Trash2, X } from 'lucide-react'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import CategoryBadge from './CategoryBadge'
import { CATEGORY_CONFIG, MAX_CHARS } from './memoryConfig'

function MemoryCard({ memory, isDeleting, onEdit, onDelete }) {
  const [editing, setEditing]   = useState(false)
  const [content, setContent]   = useState(memory.content)
  const [loading, setLoading]   = useState(false)
  const isReadOnly = memory.category === 'user_insight'
  const isAgent    = memory.metadata?.source === 'agent'
  const catCfg     = CATEGORY_CONFIG[memory.category] || CATEGORY_CONFIG.chat_insight

  const handleSave = async () => {
    if (!content.trim() || content.length > MAX_CHARS) return
    setLoading(true)
    try {
      await onEdit(memory.id, content.trim())
      setEditing(false)
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: isDeleting ? 0.5 : 1, y: 0 }}
      exit={{ opacity: 0, y: -8, height: 0 }}
      transition={{ duration: 0.18 }}
      className="rounded-xl overflow-hidden transition-opacity"
      style={{
        background:   'var(--surface)',
        border:       `1px solid var(--border)`,
        borderLeft:   `3px solid ${catCfg.color}`,
        boxShadow:    'var(--shadow-sm)',
      }}
    >
      <div className="p-4">
        {editing ? (
          <div className="space-y-2.5">
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              maxLength={MAX_CHARS}
              rows={3}
              className="w-full rounded-lg px-3 py-2.5 text-[15px] resize-none outline-hidden"
              style={{
                background:  'var(--surface-hover)',
                border:      '1px solid var(--border-focus)',
                color:       'var(--fg)',
              }}
              autoFocus
            />
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono" style={{ color: 'var(--fg-soft)' }}>
                {content.length}/{MAX_CHARS}
              </span>
              <div className="flex gap-2">
                <Button size="icon-sm" variant="ghost" onClick={() => { setContent(memory.content); setEditing(false) }}>
                  <X size={13} />
                </Button>
                <Button size="icon-sm" variant="primary" loading={loading} onClick={handleSave}>
                  <Check size={13} />
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-[15px] leading-relaxed whitespace-pre-wrap break-words" style={{ color: 'var(--fg)' }}>
                {memory.content}
              </p>
              <div className="flex items-center gap-3 mt-3 flex-wrap">
                <CategoryBadge category={memory.category} />
                {isAgent && (
                  <div className="flex items-center gap-1">
                    <Bot size={10} style={{ color: 'var(--fg-soft)' }} />
                    <span className="text-xs" style={{ color: 'var(--fg-soft)' }}>Agent</span>
                  </div>
                )}
                <span className="text-xs" style={{ color: 'var(--fg-soft)' }}>
                  {new Date(memory.updated_at || memory.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
            {!isReadOnly && (
              <div className="flex flex-col gap-1 shrink-0">
                <button
                  onClick={() => setEditing(true)}
                  disabled={isDeleting}
                  className="p-1.5 rounded-md transition-colors outline-hidden"
                  style={{ color: 'var(--fg-soft)' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--fg)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--fg-soft)' }}
                  aria-label="Edit memory"
                >
                  <Edit2 size={13} />
                </button>
                <button
                  onClick={() => onDelete(memory)}
                  disabled={isDeleting}
                  className="p-1.5 rounded-md transition-colors outline-hidden"
                  style={{ color: 'var(--fg-soft)' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--danger-soft)'; e.currentTarget.style.color = 'var(--danger)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--fg-soft)' }}
                  aria-label="Delete memory"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            )}
            {isReadOnly && (
              <div className="shrink-0 p-1.5" title="Agent-managed, read-only">
                <Lock size={12} style={{ color: 'var(--fg-soft)' }} />
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}

export default memo(MemoryCard)
