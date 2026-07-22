/** Long-term memory management — premium redesign */
'use client'

import { useState, useEffect } from 'react'
import { useSelector } from 'react-redux'
import { Brain, Plus, Edit2, Trash2, Lock, Bot, X, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { toast } from 'sonner'
import memoryService from '@/features/memory/services/memoryService'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import PageHeader from '@/components/ui/PageHeader'
import EmptyState from '@/components/ui/EmptyState'
import { ConfirmModal } from '@/components/ui/Modal'
import { cn } from '@/lib/utils'

const MAX_CHARS = 120

const CATEGORY_CONFIG = {
  user_preference: { label: 'Preference', color: 'var(--info)',    bg: 'var(--info-soft)',    variant: 'info'    },
  user_background: { label: 'Background', color: 'var(--accent)',  bg: 'var(--accent-soft)',  variant: 'accent'  },
  chat_insight:    { label: 'Insight',    color: 'var(--success)', bg: 'var(--success-soft)', variant: 'success' },
  user_insight:    { label: 'Insight',    color: 'var(--fg-soft)', bg: 'var(--surface-hover)',variant: 'default' },
}

const CATEGORY_OPTIONS = [
  { value: 'user_preference', label: 'User Preference' },
  { value: 'user_background', label: 'User Background' },
  { value: 'chat_insight',    label: 'Chat Insight'    },
]

function CategoryBadge({ category }) {
  const cfg = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.chat_insight
  const isReadOnly = category === 'user_insight'
  return (
    <div className="flex items-center gap-1">
      {isReadOnly && <Lock size={10} style={{ color: 'var(--fg-soft)' }} />}
      <Badge
        size="xs"
        style={{ background: cfg.bg, color: cfg.color, borderColor: 'transparent' }}
      >
        {cfg.label}
      </Badge>
    </div>
  )
}

/* ── Add form (expandable) ──────────────────────────────── */
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
          <span className="text-sm font-semibold" style={{ color: 'var(--fg)' }}>New Memory</span>
          <button onClick={onCancel} className="p-1 rounded" style={{ color: 'var(--fg-soft)' }}>
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
              className="w-full rounded-lg px-3 py-2.5 text-sm resize-none outline-none transition-all duration-150"
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
                className="text-[10px] font-mono"
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
                  className="px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 outline-none"
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

/* ── Memory card ────────────────────────────────────────── */
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
              className="w-full rounded-lg px-3 py-2.5 text-sm resize-none outline-none"
              style={{
                background:  'var(--surface-hover)',
                border:      '1px solid var(--border-focus)',
                color:       'var(--fg)',
              }}
              autoFocus
            />
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono" style={{ color: 'var(--fg-soft)' }}>
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
              <p className="text-sm leading-relaxed whitespace-pre-wrap break-words" style={{ color: 'var(--fg)' }}>
                {memory.content}
              </p>
              <div className="flex items-center gap-3 mt-3 flex-wrap">
                <CategoryBadge category={memory.category} />
                {isAgent && (
                  <div className="flex items-center gap-1">
                    <Bot size={10} style={{ color: 'var(--fg-soft)' }} />
                    <span className="text-[10px]" style={{ color: 'var(--fg-soft)' }}>Agent</span>
                  </div>
                )}
                <span className="text-[10px]" style={{ color: 'var(--fg-soft)' }}>
                  {new Date(memory.updated_at || memory.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
            {!isReadOnly && (
              <div className="flex flex-col gap-1 shrink-0">
                <button
                  onClick={() => setEditing(true)}
                  disabled={isDeleting}
                  className="p-1.5 rounded-md transition-colors outline-none"
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
                  className="p-1.5 rounded-md transition-colors outline-none"
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

/* ── Main component ─────────────────────────────────────── */
export default function LongTermMemoryTab() {
  const [memories, setMemories]         = useState([])
  const [loading, setLoading]           = useState(false)
  const [showAddForm, setShowAddForm]   = useState(false)
  const [deletingIds, setDeletingIds]   = useState(new Set())
  const [deleteModal, setDeleteModal]   = useState({ open: false, memory: null })

  const chatDeletedVersion = useSelector((state) => state.events.chatDeletedVersion)

  useEffect(() => { loadMemories() }, [chatDeletedVersion]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadMemories = async () => {
    try {
      setLoading(true)
      const data = await memoryService.getMemories()
      setMemories(data.memories || [])
    } catch (err) {
      console.error('Error loading memories:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async (content, category) => {
    await memoryService.createMemory(content, category)
    await loadMemories()
    setShowAddForm(false)
    toast.success('Memory saved')
  }

  const handleEdit = async (id, content) => {
    await memoryService.updateMemory(id, content)
    await loadMemories()
    toast.success('Memory updated')
  }

  const handleDeleteClick = (memory) => setDeleteModal({ open: true, memory })

  const handleConfirmDelete = async () => {
    const { memory } = deleteModal
    if (!memory) return
    setDeletingIds(prev => new Set(prev).add(memory.id))
    try {
      await memoryService.deleteMemory(memory.id)
      await loadMemories()
      toast.success('Memory deleted')
    } catch (err) {
      toast.error('Delete failed')
    } finally {
      setDeletingIds(prev => { const n = new Set(prev); n.delete(memory.id); return n })
      setDeleteModal({ open: false, memory: null })
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4 md:px-6 md:py-5">
      <div className="max-w-2xl mx-auto">
        <PageHeader
          title="Long-Term Memory"
          description={`${memories.length} memor${memories.length === 1 ? 'y' : 'ies'} stored`}
          icon={Brain}
          actions={
            <Button
              variant={showAddForm ? 'ghost' : 'primary'}
              size="sm"
              onClick={() => setShowAddForm(!showAddForm)}
              leftIcon={showAddForm ? <X size={13} /> : <Plus size={13} />}
            >
              {showAddForm ? 'Cancel' : 'Add Memory'}
            </Button>
          }
        />

        {/* Add form */}
        <AnimatePresence>
          {showAddForm && (
            <AddMemoryForm
              onAdd={handleAdd}
              onCancel={() => setShowAddForm(false)}
            />
          )}
        </AnimatePresence>

        {/* Memory list */}
        {loading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-24 rounded-xl animate-shimmer" style={{ borderLeft: '3px solid var(--border)' }} />
            ))}
          </div>
        ) : memories.length === 0 ? (
          <EmptyState
            icon={Brain}
            title="No memories yet"
            description="Long-term memories help the AI remember your preferences and context across conversations. Add your first memory to get started."
            action={
              <Button variant="primary" size="sm" onClick={() => setShowAddForm(true)}
                leftIcon={<Plus size={13} />}>
                Add Memory
              </Button>
            }
          />
        ) : (
          <motion.div className="space-y-2.5" layout>
            <AnimatePresence mode="popLayout">
              {memories.map(m => (
                <MemoryCard
                  key={m.id}
                  memory={m}
                  isDeleting={deletingIds.has(m.id)}
                  onEdit={handleEdit}
                  onDelete={handleDeleteClick}
                />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </div>

      <ConfirmModal
        open={deleteModal.open}
        onOpenChange={open => setDeleteModal(prev => ({ ...prev, open }))}
        title="Delete memory?"
        description="This memory will be permanently removed. This cannot be undone."
        confirmLabel="Delete"
        onConfirm={handleConfirmDelete}
        variant="danger"
        loading={deleteModal.memory ? deletingIds.has(deleteModal.memory.id) : false}
      />
    </div>
  )
}
