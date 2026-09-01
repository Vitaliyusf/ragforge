/** Searchable conversation history for the chat workspace. */
'use client'

import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Plus, Pencil, Trash2, MessageSquare, Loader2, AlertCircle, Search } from 'lucide-react'
import Button from '@/components/ui/Button'
import { formatChatDate } from '@/lib/formatting/datetime'
import { useI18n } from '@/i18n'

export default function ChatSidebar({
  chats,
  currentChatId,
  chatsLoading,
  chatsError,
  loading,
  deletingChatIds,
  generatingTitleChatIds,
  onSetCurrentChatId,
  onCreateNewChat,
  onRenameChat,
  onDeleteChat,
  onLoadChats,
}) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const filteredChats = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    if (!normalizedQuery) return chats
    return chats.filter((chat) => (chat.title || '').toLocaleLowerCase().includes(normalizedQuery))
  }, [chats, query])

  return (
    <div
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border"
      style={{ background: 'var(--glass)', borderColor: 'var(--border)', boxShadow: 'var(--shadow-sm)' }}
    >
      <div className="shrink-0 space-y-3 border-b p-3" style={{ borderColor: 'var(--border)' }}>
        <Button
          onClick={onCreateNewChat}
          disabled={loading}
          variant="primary"
          size="sm"
          className="w-full justify-center"
          leftIcon={<Plus size={14} />}
          aria-label={t('chat.newChat')}
        >
          {t('chat.newConversation')}
        </Button>

        <label className="relative block">
          <Search
            size={13}
            className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--fg-soft)' }}
          />
          <span className="sr-only">{t('chat.search')}</span>
          {/* `dir="auto"` on the query itself: a reader in a Hebrew shell may
              still be searching for an English chat title, and forcing the
              field RTL would put their caret on the wrong side of it. */}
          <input
            type="search"
            dir="auto"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('chat.search')}
            className="h-9 w-full rounded-xl border bg-transparent ps-9 pe-3 text-[13px] text-[var(--fg)] outline-hidden transition-all placeholder:text-[var(--fg-soft)] focus:border-[var(--border-focus)] focus:ring-2 focus:ring-[var(--ring)]"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          />
        </label>
      </div>

      <div className="flex shrink-0 items-center justify-between px-3 pb-1 pt-3">
        <span className="label-xs">{t('chat.recent')}</span>
        {!chatsLoading && (
          <span className="text-xs tabular-nums text-[var(--fg-soft)]">{filteredChats.length}</span>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        {chatsLoading ? (
          <div className="mt-1 space-y-1.5">
            {[...Array(5)].map((_, index) => (
              <div key={index} className="h-14 rounded-xl animate-shimmer" />
            ))}
          </div>
        ) : chatsError ? (
          <div className="flex flex-col items-center gap-2 px-3 py-8 text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--danger-soft)] text-[var(--danger)]">
              <AlertCircle size={18} />
            </span>
            <p className="text-[13px] leading-relaxed text-[var(--fg-muted)]">{chatsError}</p>
            <Button onClick={onLoadChats} variant="secondary" size="xs">{t('common.tryAgain')}</Button>
          </div>
        ) : chats.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-3 py-10 text-center">
            <span
              className="flex h-11 w-11 items-center justify-center rounded-2xl"
              style={{ background: 'var(--primary-soft)', color: 'var(--primary)' }}
            >
              <MessageSquare size={19} />
            </span>
            <div>
              <p className="text-[13px] font-medium text-[var(--fg)]">{t('chat.noConversations')}</p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--fg-soft)]">
                {t('chat.noConversationsHint')}
              </p>
            </div>
          </div>
        ) : filteredChats.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-[13px] font-medium text-[var(--fg)]">{t('chat.noMatching')}</p>
            <button
              type="button"
              onClick={() => setQuery('')}
              className="mt-2 text-xs font-medium text-[var(--primary)] hover:underline"
            >
              {t('chat.clearSearch')}
            </button>
          </div>
        ) : (
          filteredChats.map((chat, index) => (
            <ChatItem
              key={chat.id}
              chat={chat}
              index={index}
              isActive={currentChatId === chat.id}
              isDeleting={deletingChatIds.has(chat.id)}
              isGeneratingTitle={generatingTitleChatIds.has(chat.id)}
              onSelect={() => {
                if (!deletingChatIds.has(chat.id)) onSetCurrentChatId(chat.id)
              }}
              onRename={onRenameChat}
              onDelete={(event) => {
                event.stopPropagation()
                if (!deletingChatIds.has(chat.id)) onDeleteChat(chat.id)
              }}
            />
          ))
        )}
      </div>
    </div>
  )
}

function ChatItem({ chat, isActive, isDeleting, isGeneratingTitle, onSelect, onRename, onDelete, index }) {
  const { locale, isRTL, t } = useI18n()
  const [draftTitle, setDraftTitle] = useState(null)
  const isEditing = draftTitle != null

  const commitRename = () => {
    const next = (draftTitle || '').trim()
    setDraftTitle(null)
    if (next && next !== chat.title) onRename?.(chat.id, next)
  }

  if (isEditing) {
    return (
      <div className="mb-1 flex items-center gap-2 rounded-xl border px-2.5 py-2.5" style={{ borderColor: 'var(--border)' }}>
        <input
          autoFocus
          dir="auto"
          value={draftTitle}
          aria-label={t('chat.renameChat', { title: chat.title })}
          onChange={(event) => setDraftTitle(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              commitRename()
            }
            if (event.key === 'Escape') {
              event.preventDefault()
              setDraftTitle(null)
            }
          }}
          className="h-7 w-full rounded-lg border bg-transparent px-2 text-[13px] text-[var(--fg)] outline-hidden focus:border-[var(--border-focus)] focus:ring-2 focus:ring-[var(--ring)]"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        />
      </div>
    )
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: isRTL ? 6 : -6 }}
      animate={{ opacity: isDeleting ? 0.5 : 1, x: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.025 }}
      className="group relative mb-1 flex cursor-pointer items-center gap-2 rounded-xl border px-2.5 py-2.5 outline-hidden transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
      style={{
        background: isActive ? 'var(--primary-soft)' : 'transparent',
        borderColor: isActive ? 'rgba(var(--primary-rgb) / 0.22)' : 'transparent',
      }}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect()
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={t('chat.selectChat', { title: chat.title })}
    >
      <span
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
        style={{
          background: isActive ? 'var(--surface)' : 'var(--surface-hover)',
          color: isActive ? 'var(--primary)' : 'var(--fg-soft)',
        }}
      >
        {isGeneratingTitle
          ? <Loader2 size={13} className="animate-spin" />
          : <MessageSquare size={13} />}
      </span>

      <div className="min-w-0 flex-1">
        <span
          dir="auto"
          className="block truncate text-[13px] font-medium"
          style={{ color: isActive ? 'var(--fg)' : 'var(--fg-muted)' }}
        >
          {chat.title}
        </span>
        <span className="mt-0.5 block text-xs text-[var(--fg-soft)]">
          {formatChatDate(chat.updated_at, locale)}
        </span>
      </div>

      {onRename ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            setDraftTitle(chat.title || '')
          }}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--fg-soft)] opacity-0 transition-all hover:bg-[var(--surface-hover)] hover:text-[var(--fg)] focus-visible:opacity-100 focus-visible:outline-hidden group-hover:opacity-100"
          aria-label={t('chat.renameChat', { title: chat.title })}
        >
          <Pencil size={12} />
        </button>
      ) : null}

      <button
        type="button"
        onClick={onDelete}
        disabled={isDeleting}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--fg-soft)] opacity-0 transition-all hover:bg-[var(--danger-soft)] hover:text-[var(--danger)] focus-visible:opacity-100 focus-visible:outline-hidden group-hover:opacity-100"
        aria-label={t('chat.deleteChat', { title: chat.title })}
      >
        {isDeleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
      </button>
    </motion.div>
  )
}
