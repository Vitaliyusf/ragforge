'use client'

import { useCallback, useMemo, useState } from 'react'
import {
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  ServerCrash,
  Sparkles,
} from 'lucide-react'
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
import { useI18n } from '@/i18n'

export default function ChatTab() {
  const { isAdmin } = useAuth()
  const { isRTL, t } = useI18n()
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

  // The mobile history drawer lives on the *start* edge — left in English,
  // right in Hebrew — so it enters from the side the reader's eye already
  // treats as the beginning of the line. The offset and the panel glyphs are
  // mirrored with it; a drawer that slid in from the wrong edge behind a
  // left-pointing icon would be two mistakes, not one.
  const drawerOffset = isRTL ? 320 : -320
  // The inspector is an auxiliary panel and belongs on the logical end —
  // right in English, left in Hebrew — so it enters from the edge it rests on.
  const inspectorOffset = isRTL ? -32 : 32
  const OpenDrawerIcon = isRTL ? PanelRightOpen : PanelLeftOpen
  const CloseDrawerIcon = isRTL ? PanelRightClose : PanelLeftClose

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
                aria-label={t('chat.closeHistory')}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-xs xl:hidden"
                onClick={() => setSidebarOpen(false)}
              />
              <motion.aside
                initial={{ x: drawerOffset }}
                animate={{ x: 0 }}
                exit={{ x: drawerOffset }}
                transition={{ type: 'spring', damping: 30, stiffness: 400 }}
                className="fixed inset-y-0 start-0 z-[80] flex w-[min(20rem,calc(100vw-2rem))] flex-col gap-3 overflow-hidden border-e p-3 xl:hidden"
                style={{
                  background: 'var(--bg)',
                  borderColor: 'var(--border)',
                  boxShadow: 'var(--shadow-xl)',
                }}
              >
                <div className="flex h-10 shrink-0 items-center justify-between px-1">
                  <span className="text-[15px] font-semibold text-[var(--fg)]">{t('chat.workspace')}</span>
                  <button
                    type="button"
                    onClick={() => setSidebarOpen(false)}
                    className="flex h-8 w-8 items-center justify-center rounded-xl text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]"
                    aria-label={t('chat.closeHistoryPanel')}
                  >
                    <CloseDrawerIcon size={16} />
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
              aria-label={t('chat.toggleHistory')}
            >
              <OpenDrawerIcon size={17} />
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
                {activeChat?.title || t('chat.newConversation')}
              </h1>
              <p className="mt-0.5 text-xs text-[var(--fg-soft)]">
                {messages.length === 0
                  ? t('chat.emptyThreadSubtitle')
                  : t('chat.messageCount', { count: messages.length })}
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
                aria-label={t('chat.closeInspectorOverlay')}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 z-30 bg-black/20 backdrop-blur-[2px]"
                onClick={closeInspector}
              />
              <motion.div
                initial={{ opacity: 0, x: inspectorOffset }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: inspectorOffset }}
                transition={{ type: 'spring', damping: 30, stiffness: 360 }}
                className="absolute inset-y-3 end-3 z-40 w-[min(430px,calc(100%-1.5rem))] md:inset-y-4 md:end-4"
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
          title={t('chat.deleteTitle')}
          // The delete_chat handler drops the chat, its messages and the
          // memories indexed against it; long-term memory is a separate store
          // and survives, so the copy says so rather than implying otherwise.
          description={
            chatToDelete ? t('chat.deleteDescription', { title: chatToDelete.title }) : ''
          }
          confirmLabel={t('common.delete')}
          onConfirm={handleConfirmDelete}
          variant="danger"
          loading={chatToDelete ? deletingChatIds.has(chatToDelete.id) : false}
        />
      </div>
    </MotionConfig>
  )
}
