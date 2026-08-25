'use client'

import { useMemo, useState } from 'react'
import { PanelLeftOpen, PanelLeftClose, Sparkles, Loader2, ServerCrash } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useChat } from '@/features/chat'
import { useAuth } from '@/features/auth'
import { useChatInit } from '@/features/chat/hooks/useChatInit'
import { useLlmReadiness } from '@/features/chat/hooks/useLlmReadiness'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import ChatSidebar from './ChatSidebar'
import ModelSelector from './ModelSelector'
import TraceDebugPanel from './TraceDebugPanel'
import { ConfirmModal } from '@/components/ui/Modal'

export default function ChatTab() {
  const { isAdmin } = useAuth()
  const {
    messages, turnsById, chats, currentChatId, loading, chatsLoading, chatsError,
    models, selectedModel, defaultModel, wsConnectionStatus, answerMode,
    sendingMessage, deletingChatIds, generatingTitleChatIds, extendedProgress,
    selectChat, setSelectedModel, setAnswerMode, createNewChat,
    sendMessage, sendAnswerFeedback, sendFlowFeedback, deleteChat, loadChats,
  } = useChat()

  const { suggestedPrompts } = useChatInit()
  const { llmReady, llmChecked } = useLlmReadiness()

  const [inputValue, setInputValue] = useState('')
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [chatToDelete, setChatToDelete] = useState(null)
  const [selectedDebugMessageId, setSelectedDebugMessageId] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const selectedDebugMessage = useMemo(
    () => messages.find((message) => message.id === selectedDebugMessageId) || null,
    [messages, selectedDebugMessageId]
  )
  const selectedDebugTurn = selectedDebugMessage?.turnId
    ? turnsById[selectedDebugMessage.turnId]
    : null
  const activeChat = useMemo(
    () => chats.find((chat) => chat.id === currentChatId) || null,
    [chats, currentChatId]
  )

  // The LLM readiness gate takes priority over the WebSocket transport status:
  // there's no point advertising "Live" if vLLM can't answer yet.
  const statusPill = !llmReady
    ? (llmChecked
        ? { label: 'LLM not available', tone: 'error' }
        : { label: 'Checking LLM…', tone: 'neutral' })
    : wsConnectionStatus === 'connected'
      ? { label: 'Live', tone: 'success' }
      : wsConnectionStatus === 'connecting'
        ? { label: 'Connecting', tone: 'neutral' }
        : { label: 'Offline', tone: 'neutral' }

  const handleSend = (text) => {
    if (!llmReady) return
    const nextText = text ?? inputValue.trim()
    if (!nextText) return
    setInputValue('')
    sendMessage(nextText)
  }

  const handleDeleteClick = (chatId) => {
    const chat = chats.find((item) => item.id === chatId)
    setChatToDelete(chat)
    setDeleteModalOpen(true)
  }

  const handleConfirmDelete = async () => {
    if (!chatToDelete) return
    await deleteChat(chatToDelete.id)
    setChatToDelete(null)
  }

  const sidebar = (mobile = false) => (
    <>
      <ChatSidebar
        chats={chats}
        currentChatId={currentChatId}
        chatsLoading={chatsLoading}
        chatsError={chatsError}
        loading={loading}
        deletingChatIds={deletingChatIds}
        generatingTitleChatIds={generatingTitleChatIds}
        onSetCurrentChatId={(id) => {
          selectChat(id)
          if (mobile) setSidebarOpen(false)
        }}
        onCreateNewChat={() => {
          createNewChat()
          if (mobile) setSidebarOpen(false)
        }}
        onDeleteChat={handleDeleteClick}
        onLoadChats={loadChats}
      />
      <ModelSelector
        models={models}
        selectedModel={selectedModel}
        defaultModel={defaultModel}
        onSelectModel={setSelectedModel}
      />
    </>
  )

  return (
    <div className="relative flex min-h-0 flex-1 gap-4 overflow-hidden p-3 md:p-4">
      <aside className="hidden w-[276px] shrink-0 flex-col gap-3 overflow-hidden xl:flex">
        {sidebar()}
      </aside>

      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.button
              type="button"
              aria-label="Close chat history"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-sm xl:hidden"
              onClick={() => setSidebarOpen(false)}
            />
            <motion.aside
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ type: 'spring', damping: 30, stiffness: 400 }}
              className="fixed inset-y-0 left-0 z-[80] flex w-[min(20rem,calc(100vw-2rem))] flex-col gap-3 overflow-hidden p-3 xl:hidden"
              style={{
                background: 'var(--bg)',
                borderRight: '1px solid var(--border)',
                boxShadow: 'var(--shadow-xl)',
              }}
            >
              <div className="flex h-10 shrink-0 items-center justify-between px-1">
                <span className="text-[15px] font-semibold text-[var(--fg)]">Chat workspace</span>
                <button
                  type="button"
                  onClick={() => setSidebarOpen(false)}
                  className="flex h-8 w-8 items-center justify-center rounded-xl text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]"
                  aria-label="Close chat history panel"
                >
                  <PanelLeftClose size={16} />
                </button>
              </div>
              {sidebar(true)}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <section
        className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-3xl"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow-md)',
        }}
      >
        <div
          className="flex h-[58px] shrink-0 items-center gap-3 border-b px-3 md:px-5"
          style={{ borderColor: 'var(--border)', background: 'var(--glass)' }}
        >
          <button
            type="button"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)] xl:hidden"
            onClick={() => setSidebarOpen(true)}
            aria-label="Toggle chat history"
          >
            <PanelLeftOpen size={17} />
          </button>

          <div
            className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-xl sm:flex"
            style={{ background: 'var(--gradient-subtle)', color: 'var(--primary)' }}
          >
            <Sparkles size={16} />
          </div>

          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[15px] font-semibold text-[var(--fg)]">
              {activeChat?.title || 'New conversation'}
            </h1>
            <p className="mt-0.5 text-xs text-[var(--fg-soft)]">
              {messages.length === 0
                ? 'Ask your knowledge base anything'
                : `${messages.length} message${messages.length === 1 ? '' : 's'} in this thread`}
            </p>
          </div>

          <div
            className="hidden items-center gap-2 rounded-full border px-2.5 py-1.5 text-xs font-medium sm:flex"
            style={{
              background: statusPill.tone === 'success'
                ? 'var(--success-soft)'
                : statusPill.tone === 'error'
                  ? 'var(--danger-soft)'
                  : 'var(--surface-hover)',
              borderColor: statusPill.tone === 'success'
                ? 'rgba(34,197,94,0.22)'
                : statusPill.tone === 'error'
                  ? 'rgba(239,68,68,0.22)'
                  : 'var(--border)',
              color: statusPill.tone === 'success'
                ? 'var(--success)'
                : statusPill.tone === 'error'
                  ? 'var(--danger)'
                  : 'var(--fg-soft)',
            }}
          >
            <span
              className={statusPill.label === 'Checking LLM…'
                ? 'h-1.5 w-1.5 animate-pulse rounded-full'
                : 'h-1.5 w-1.5 rounded-full'}
              style={{ background: 'currentColor' }}
            />
            {statusPill.label}
          </div>
        </div>

        {!llmReady && (
          <div
            className="flex shrink-0 items-center gap-2.5 border-b px-4 py-2.5 text-[13px]"
            style={{
              borderColor: 'var(--border)',
              background: llmChecked ? 'var(--danger-soft)' : 'var(--surface-hover)',
              color: llmChecked ? 'var(--danger)' : 'var(--fg-muted)',
            }}
          >
            {llmChecked
              ? <ServerCrash size={14} className="shrink-0" />
              : <Loader2 size={14} className="shrink-0 animate-spin" />}
            <span>
              {llmChecked
                ? 'The language model isn’t available yet — it’s still starting up. Chat will enable automatically once it’s ready.'
                : 'Checking whether the language model is available…'}
            </span>
          </div>
        )}

        <MessageList
          messages={messages}
          turnsById={turnsById}
          suggestedPrompts={suggestedPrompts}
          onSuggestedPrompt={handleSend}
          onOpenDebug={(message) => setSelectedDebugMessageId(message.id)}
          canViewDebug={isAdmin}
          onAnswerFeedback={sendAnswerFeedback}
          onFlowFeedback={sendFlowFeedback}
          extendedProgress={extendedProgress}
        />

        <ChatInput
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          onSend={() => handleSend()}
          sendingMessage={sendingMessage}
          answerMode={answerMode}
          onAnswerModeChange={setAnswerMode}
          wsConnectionStatus={wsConnectionStatus}
          llmReady={llmReady}
          llmChecked={llmChecked}
        />
      </section>

      <AnimatePresence>
        {isAdmin && selectedDebugMessage && (
          <>
            <motion.button
              type="button"
              aria-label="Close trace overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 z-30 bg-black/20 backdrop-blur-[2px]"
              onClick={() => setSelectedDebugMessageId(null)}
            />
            <motion.div
              initial={{ opacity: 0, x: 32 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 32 }}
              transition={{ type: 'spring', damping: 30, stiffness: 360 }}
              className="absolute inset-y-3 right-3 z-40 w-[min(430px,calc(100%-1.5rem))] md:inset-y-4 md:right-4"
              style={{ filter: 'drop-shadow(0 24px 48px rgba(0,0,0,0.24))' }}
            >
              <TraceDebugPanel
                message={selectedDebugMessage}
                turn={selectedDebugTurn}
                onClose={() => setSelectedDebugMessageId(null)}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <ConfirmModal
        open={deleteModalOpen}
        onOpenChange={setDeleteModalOpen}
        title="Delete chat?"
        description={chatToDelete ? `Delete "${chatToDelete.title}"? This cannot be undone.` : ''}
        confirmLabel="Delete"
        onConfirm={handleConfirmDelete}
        variant="danger"
        loading={chatToDelete ? deletingChatIds.has(chatToDelete.id) : false}
      />
    </div>
  )
}
