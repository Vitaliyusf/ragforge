'use client'

import { useCallback, useMemo, useState } from 'react'
import { PanelLeftOpen, PanelLeftClose, Sparkles, Loader2, ServerCrash } from 'lucide-react'
import { AnimatePresence, MotionConfig, motion } from 'framer-motion'
import { useChat } from '@/features/chat'
import { useAuth } from '@/features/auth'
import { useChatInit } from '@/features/chat/hooks/useChatInit'
import { useLlmReadiness } from '@/features/chat/hooks/useLlmReadiness'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import ChatSidebar from './ChatSidebar'
import ModelSelector from './ModelSelector'
import DeveloperInspector from './inspector/DeveloperInspector'
import { ConfirmModal } from '@/components/ui/Modal'

export default function ChatTab() {
  const { isAdmin } = useAuth()
  const {
    messages, turnsById, chats, currentChatId, loading, chatsLoading, chatsError,
    models, selectedModel, defaultModel, wsConnectionStatus, answerMode,
    sendingMessage, deletingChatIds, generatingTitleChatIds, activityStatus,
    selectChat, setSelectedModel, setAnswerMode, createNewChat,
    sendMessage, sendAnswerFeedback, sendFlowFeedback, renameChat, deleteChat, loadChats,
  } = useChat()

  const { suggestedPrompts } = useChatInit()
  const { llmReady, llmChecked } = useLlmReadiness()

  const [inputValue, setInputValue] = useState('')
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [chatToDelete, setChatToDelete] = useState(null)
  const [inspectedMessageId, setInspectedMessageId] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const inspectedMessage = useMemo(
    () => messages.find((message) => message.id === inspectedMessageId) || null,
    [messages, inspectedMessageId]
  )
  const inspectedTurn = inspectedMessage?.turnId ? turnsById[inspectedMessage.turnId] : null
  const activeChat = useMemo(
    () => chats.find((chat) => chat.id === currentChatId) || null,
    [chats, currentChatId]
  )

  const handleSend = (text) => {
    if (!llmReady) return
    const nextText = text ?? inputValue.trim()
    if (!nextText) return
    setInputValue('')
    sendMessage(nextText)
  }

  // Stable identities: every message bubble is memoised, so a callback that
  // changed on each render of this component would re-render the whole thread.
  const handleOpenInspector = useCallback((message) => setInspectedMessageId(message.id), [])
  const closeInspector = useCallback(() => setInspectedMessageId(null), [])

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
        onRenameChat={renameChat}
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
    // Every transition in the chat surface honours the reader's reduced-motion
    // preference rather than each component remembering to check.
    <MotionConfig reducedMotion="user">
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
                className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-xs xl:hidden"
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
              style={{ color: 'var(--primary)' }}
            >
              <Sparkles size={16} />
            </div>

            {/* The header carries the conversation, not a second copy of the
                transport state: connection and LLM readiness are reported once,
                in the composer. */}
            <div className="min-w-0 flex-1">
              <h1 dir="auto" className="truncate text-[15px] font-semibold text-[var(--fg)]">
                {activeChat?.title || 'New conversation'}
              </h1>
              <p className="mt-0.5 text-xs text-[var(--fg-soft)]">
                {messages.length === 0
                  ? 'Ask your knowledge base anything'
                  : `${messages.length} message${messages.length === 1 ? '' : 's'} in this thread`}
              </p>
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
            onOpenInspector={handleOpenInspector}
            canInspect={isAdmin}
            onAnswerFeedback={sendAnswerFeedback}
            activityStatus={activityStatus}
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
          {isAdmin && inspectedMessage && (
            <>
              <motion.button
                type="button"
                aria-label="Close inspector overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 z-30 bg-black/20 backdrop-blur-[2px]"
                onClick={closeInspector}
              />
              <motion.div
                initial={{ opacity: 0, x: 32 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 32 }}
                transition={{ type: 'spring', damping: 30, stiffness: 360 }}
                className="absolute inset-y-3 right-3 z-40 w-[min(430px,calc(100%-1.5rem))] md:inset-y-4 md:right-4"
                style={{ filter: 'drop-shadow(0 24px 48px rgba(0,0,0,0.24))' }}
              >
                <DeveloperInspector
                  message={inspectedMessage}
                  turn={inspectedTurn}
                  onClose={closeInspector}
                  onFlowFeedback={sendFlowFeedback}
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
    </MotionConfig>
  )
}
