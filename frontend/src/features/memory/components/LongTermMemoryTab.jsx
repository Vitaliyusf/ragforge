/** Long-term memory management — premium redesign */
'use client'

import { useState, useEffect } from 'react'
import { useSelector } from 'react-redux'
import { Brain, Plus, Edit2, Trash2, Lock, Bot, X, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { notifyError, notifySuccess } from '@/lib/notify'
import memoryService from '@/features/memory/services/memoryService'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import PageHeader from '@/components/ui/PageHeader'
import EmptyState from '@/components/feedback/EmptyState'
import ErrorState from '@/components/feedback/ErrorState'
import { ConfirmModal } from '@/components/ui/Modal'
import { cn } from '@/lib/utils'
import AddMemoryForm from './AddMemoryForm'
import MemoryCard from './MemoryCard'
import { CATEGORY_OPTIONS } from './memoryConfig'

/** Enough of the memory to recognise which one is about to go. */
const truncate = (text = '') => (text.length > 80 ? `${text.slice(0, 80)}…` : text)

export default function LongTermMemoryTab() {
  const [memories, setMemories]         = useState([])
  const [loading, setLoading]           = useState(false)
  const [showAddForm, setShowAddForm]   = useState(false)
  const [deletingIds, setDeletingIds]   = useState(new Set())
  const [deleteModal, setDeleteModal]   = useState({ open: false, memory: null })
  const [loadError, setLoadError]       = useState(null)

  const chatDeletedVersion = useSelector((state) => state.events.chatDeletedVersion)

  useEffect(() => { loadMemories() }, [chatDeletedVersion]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadMemories = async () => {
    try {
      setLoading(true)
      const data = await memoryService.getMemories()
      setMemories(data.memories || [])
      setLoadError(null)
    } catch (err) {
      // A failed load used to fall through to the empty state, which reads as
      // "you have no memories" — the one thing it does not mean.
      setLoadError(err)
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async (content, category) => {
    await memoryService.createMemory(content, category)
    await loadMemories()
    setShowAddForm(false)
    notifySuccess('Memory saved')
  }

  const handleEdit = async (id, content) => {
    await memoryService.updateMemory(id, content)
    await loadMemories()
    notifySuccess('Memory updated')
  }

  const handleDeleteClick = (memory) => setDeleteModal({ open: true, memory })

  const handleConfirmDelete = async () => {
    const { memory } = deleteModal
    if (!memory) return
    setDeletingIds(prev => new Set(prev).add(memory.id))
    try {
      await memoryService.deleteMemory(memory.id)
      await loadMemories()
      notifySuccess('Memory deleted')
    } catch (err) {
      notifyError('Delete failed', { error: err, onRetry: handleConfirmDelete })
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
        ) : loadError ? (
          <ErrorState
            title="Could not load memories"
            description="The memory service did not answer. Your stored memories are unaffected."
            detail={loadError?.message}
            action={<Button variant="secondary" size="sm" onClick={loadMemories}>Retry</Button>}
          />
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
        description={
          deleteModal.memory
            ? `"${truncate(deleteModal.memory.content)}" is removed from long-term memory, so the assistant stops using it in future conversations. Past replies that already used it are unchanged. This cannot be undone.`
            : ''
        }
        confirmLabel="Delete"
        onConfirm={handleConfirmDelete}
        variant="danger"
        loading={deleteModal.memory ? deletingIds.has(deleteModal.memory.id) : false}
      />
    </div>
  )
}
