'use client'

import { useEffect, useRef } from 'react'
import { ArrowUp, Loader2, WifiOff, ServerCrash } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Select, { SelectItem } from '@/components/ui/Select'

// A healthy connection says nothing: a permanently lit "Live" chip is noise
// that competes with the real, transient states below it. `connected` is
// therefore absent from this table, and the badge is simply not rendered.
const WS_STATUS_CONFIG = {
  connecting: { variant: 'warning', label: 'Connecting...', icon: Loader2, iconSpin: true },
  // Both of these are one connectivity state: the link is not there. They
  // used to read "Offline" and "Disconnected", which looked like two things.
  failed: { variant: 'error', label: 'Disconnected', icon: WifiOff, iconSpin: false },
  disconnected: { variant: 'default', label: 'Disconnected', icon: WifiOff, iconSpin: false },
}

// Shown in place of the transport badge while the LLM backend isn't ready.
const LLM_STARTING_CONFIG = { variant: 'warning', label: 'LLM starting...', icon: Loader2, iconSpin: true }
const LLM_UNAVAILABLE_CONFIG = { variant: 'error', label: 'LLM not available', icon: ServerCrash, iconSpin: false }

const MAX_TEXTAREA_HEIGHT = 160

export default function ChatInput({
  value,
  onChange,
  onSend,
  sendingMessage,
  answerMode,
  onAnswerModeChange,
  wsConnectionStatus,
  llmReady = true,
  llmChecked = true,
}) {
  const textareaRef = useRef(null)
  // Until the LLM backend is ready the badge reflects LLM availability rather
  // than the WebSocket transport — a healthy socket is meaningless if vLLM
  // can't answer yet. When both are healthy there is nothing to report and the
  // badge is omitted entirely.
  const statusConfig = llmReady
    ? (wsConnectionStatus === 'connected'
        ? null
        : (WS_STATUS_CONFIG[wsConnectionStatus] ?? WS_STATUS_CONFIG.disconnected))
    : (llmChecked ? LLM_UNAVAILABLE_CONFIG : LLM_STARTING_CONFIG)
  const canSend = llmReady && !sendingMessage && value.trim().length > 0
  const inputDisabled = sendingMessage || !llmReady
  const placeholder = llmReady
    ? 'Ask anything about your knowledge base...'
    : (llmChecked
        ? 'The language model is starting up — chat will enable when it’s ready'
        : 'Checking whether the language model is available…')

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`
  }, [value])

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (canSend) onSend()
    }
  }

  return (
    <div className="composer-fade shrink-0 px-3 pb-3 pt-7 md:px-5 md:pb-4">
      <div
        className="mx-auto max-w-[64rem] overflow-hidden rounded-2xl border border-[var(--border)] transition-all duration-200 focus-within:border-[var(--border-focus)] focus-within:ring-2 focus-within:ring-[var(--ring)]"
        style={{
          background: 'var(--surface-elevated)',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <div className="flex items-end gap-2 px-3 pb-2 pt-3 md:pl-4">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={onChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            aria-label="Chat message"
            disabled={inputDisabled}
            className="min-h-7 min-w-0 flex-1 resize-none overflow-y-auto bg-transparent py-1 text-[15px] leading-relaxed text-[var(--fg)] outline-hidden placeholder:text-[var(--fg-soft)] disabled:opacity-60 scrollbar-none"
            style={{ maxHeight: MAX_TEXTAREA_HEIGHT }}
          />

          <button
            type="button"
            onClick={onSend}
            disabled={!canSend}
            aria-label="Send message"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white outline-hidden transition-all duration-200 enabled:hover:brightness-110 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
            style={{
              background: canSend ? 'var(--gradient-primary)' : 'var(--surface-active)',
              color: canSend ? 'white' : 'var(--fg-soft)',
              boxShadow: canSend ? 'var(--shadow-sm)' : 'none',
            }}
          >
            {sendingMessage
              ? <Loader2 size={15} className="animate-spin" />
              : <ArrowUp size={16} strokeWidth={2.2} />}
          </button>
        </div>

        <div className="flex min-w-0 items-center gap-2 border-t px-3 py-2" style={{ borderColor: 'var(--border)' }}>
          <Select
            value={answerMode}
            onValueChange={onAnswerModeChange}
            placeholder="Mode"
            className="h-7 min-w-[108px] max-w-[126px] border-transparent px-2.5 py-0 text-xs"
            aria-label="Answer mode"
          >
            <SelectItem value="regular">Quick answer</SelectItem>
            <SelectItem value="extended">Deep research</SelectItem>
          </Select>

          {statusConfig ? (
            <>
              <div className="h-3.5 w-px shrink-0 bg-[var(--border)]" />
              <Badge
                variant={statusConfig.variant}
                icon={statusConfig.icon}
                spin={statusConfig.iconSpin}
                size="xs"
                aria-label={`Status: ${statusConfig.label}`}
              >
                {statusConfig.label}
              </Badge>
            </>
          ) : null}

          <span className="ml-auto hidden text-xs text-[var(--fg-soft)] sm:block">
            Enter to send · Shift+Enter for a new line
          </span>
        </div>
      </div>
    </div>
  )
}
