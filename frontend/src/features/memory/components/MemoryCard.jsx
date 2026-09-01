'use client'

import { memo, useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, Check, ChevronDown, ChevronUp, Edit2, Lock, Trash2, X } from 'lucide-react'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { useI18n } from '@/i18n'
import { intlLocale } from '@/lib/formatting/datetime'
import CategoryBadge from './CategoryBadge'
import { CATEGORY_CONFIG, MAX_CHARS } from './memoryConfig'

/** These controls suppress the UA outline for the app ring, so the ring is
    spelled out rather than left to the browser default. */
const FOCUS_RING =
  'focus:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface)]'

function MemoryCard({ memory, isDeleting, onEdit, onDelete }) {
  const { locale, t } = useI18n()
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
              dir="auto"
              aria-label={t('memory.editContent')}
              className={cn('w-full rounded-lg px-3 py-2.5 text-[15px] resize-none', FOCUS_RING)}
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
              {/* Memory content is user-generated and may be Hebrew,
                  English or mixed, whatever the interface is set to. */}
              <p
                dir="auto"
                className="text-[15px] leading-relaxed whitespace-pre-wrap break-words text-start"
                style={{ color: 'var(--fg)' }}
              >
                {memory.content}
              </p>
              <div className="flex items-center gap-3 mt-3 flex-wrap">
                <CategoryBadge category={memory.category} />
                {isAgent && (
                  <div className="flex items-center gap-1">
                    <Bot size={10} style={{ color: 'var(--fg-soft)' }} />
                    <span className="text-xs" style={{ color: 'var(--fg-soft)' }}>{t('memory.agent')}</span>
                  </div>
                )}
                <span className="text-xs" style={{ color: 'var(--fg-soft)' }}>
                  {new Date(memory.updated_at || memory.created_at)
                    .toLocaleDateString(intlLocale(locale))}
                </span>
              </div>
            </div>
            {!isReadOnly && (
              <div className="flex flex-col gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  disabled={isDeleting}
                  className={cn('p-1.5 rounded-md transition-colors', FOCUS_RING)}
                  style={{ color: 'var(--fg-soft)' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--fg)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--fg-soft)' }}
                  aria-label={t('memory.edit')}
                >
                  <Edit2 size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(memory)}
                  disabled={isDeleting}
                  className={cn('p-1.5 rounded-md transition-colors', FOCUS_RING)}
                  style={{ color: 'var(--fg-soft)' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--danger-soft)'; e.currentTarget.style.color = 'var(--danger)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--fg-soft)' }}
                  aria-label={t('memory.delete')}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            )}
            {isReadOnly && (
              <div
                className="flex shrink-0 items-center gap-1 self-start rounded-md px-2 py-1 text-xs"
                style={{ background: 'var(--surface-hover)', color: 'var(--fg-soft)' }}
                title={t('memory.systemManaged')}
              >
                <Lock size={12} style={{ color: 'var(--fg-soft)' }} aria-hidden="true" />
                <span>{t('memory.systemManaged')}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}

export default memo(MemoryCard)
