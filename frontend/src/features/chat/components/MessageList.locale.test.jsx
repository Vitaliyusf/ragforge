/**
 * The chat surface under a Hebrew interface.
 *
 * The existing bidi suite proves that a run of text lays out in its own
 * direction. This one proves the harder half: that the *interface* locale and
 * the *content* direction stay independent. A Hebrew reader can be handed an
 * English answer and an English reader a Hebrew one, and neither may be bent
 * to the shell. The speaker geometry — outgoing on the right — is a messaging
 * convention and must not mirror either.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import MessageList from './MessageList'
import ChatSidebar from './ChatSidebar'
import ChatInput from './ChatInput'
import { I18nProvider } from '@/i18n'

function renderMessages(messages, locale = 'he') {
  return render(
    <I18nProvider initialLocale={locale}>
      <MessageList
        messages={messages}
        turnsById={{}}
        suggestedPrompts={[]}
        onSuggestedPrompt={vi.fn()}
        onOpenInspector={vi.fn()}
        onAnswerFeedback={vi.fn()}
        canInspect={false}
        activityStatus={null}
      />
    </I18nProvider>
  )
}

const surfaceOf = (text) => screen.getByText(text).closest('[dir]')

describe('answer direction is content-driven, not locale-driven', () => {
  it('keeps an English answer left-to-right inside a Hebrew interface', () => {
    renderMessages([{ id: 'm1', sender: 'Assistant', text: 'Vector search runs first.' }], 'he')
    expect(surfaceOf('Vector search runs first.')).toHaveAttribute('dir', 'ltr')
  })

  it('keeps a Hebrew answer right-to-left inside an English interface', () => {
    renderMessages([{ id: 'm1', sender: 'Assistant', text: 'המסמך מתאר את תהליך האחזור.' }], 'en')
    expect(surfaceOf('המסמך מתאר את תהליך האחזור.')).toHaveAttribute('dir', 'rtl')
  })

  it('leaves a mixed answer to the browser in either interface', () => {
    const mixed = 'The model is gpt-4o-mini ואז המסמך.'
    const { unmount } = renderMessages([{ id: 'm1', sender: 'Assistant', text: mixed }], 'he')
    expect(surfaceOf(mixed)).toHaveAttribute('dir', 'auto')
    unmount()

    renderMessages([{ id: 'm1', sender: 'Assistant', text: mixed }], 'en')
    expect(surfaceOf(mixed)).toHaveAttribute('dir', 'auto')
  })
})

describe('speaker geometry', () => {
  it('keeps the reader\'s own message on the right in both interfaces', () => {
    for (const locale of ['en', 'he']) {
      const { unmount } = renderMessages(
        [{ id: 'm1', sender: 'You', text: 'שלום' }],
        locale
      )
      // `items-end` resolves against the wrapper's direction, so the wrapper
      // is pinned LTR: outgoing messages sit on the right in Hebrew too,
      // which is what every messaging client the reader already uses does.
      const column = screen.getByText('שלום').closest('.flex-col')
      expect(column, locale).toHaveAttribute('dir', 'ltr')
      expect(column.className, locale).toContain('items-end')
      unmount()
    }
  })

  it('names the reader in their own language without rewriting the stored sender', () => {
    renderMessages([{ id: 'm1', sender: 'You', text: 'שלום' }], 'he')
    expect(screen.getByText('אני')).toBeInTheDocument()
    expect(screen.queryByText('You')).toBeNull()
  })

  it('names the assistant in Hebrew while the stored sender stays Assistant', () => {
    renderMessages([{ id: 'm1', sender: 'Assistant', text: 'שלום' }], 'he')
    expect(screen.getByText('העוזר')).toBeInTheDocument()
  })
})

describe('chat chrome in Hebrew', () => {
  it('translates the sidebar copy and its empty state', () => {
    render(
      <I18nProvider initialLocale="he">
        <ChatSidebar
          chats={[]}
          currentChatId={null}
          chatsLoading={false}
          chatsError={null}
          loading={false}
          deletingChatIds={new Set()}
          generatingTitleChatIds={new Set()}
          onSetCurrentChatId={vi.fn()}
          onCreateNewChat={vi.fn()}
          onRenameChat={vi.fn()}
          onDeleteChat={vi.fn()}
          onLoadChats={vi.fn()}
        />
      </I18nProvider>
    )

    expect(screen.getByRole('button', { name: 'שיחה חדשה' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('חיפוש בשיחות')).toBeInTheDocument()
    expect(screen.getByText('שיחות אחרונות')).toBeInTheDocument()
    expect(screen.getByText('אין עדיין שיחות')).toBeInTheDocument()
  })

  it('accepts a mixed-script search query rather than forcing it RTL', () => {
    render(
      <I18nProvider initialLocale="he">
        <ChatSidebar
          chats={[]}
          currentChatId={null}
          chatsLoading={false}
          chatsError={null}
          loading={false}
          deletingChatIds={new Set()}
          generatingTitleChatIds={new Set()}
          onSetCurrentChatId={vi.fn()}
          onCreateNewChat={vi.fn()}
          onRenameChat={vi.fn()}
          onDeleteChat={vi.fn()}
          onLoadChats={vi.fn()}
        />
      </I18nProvider>
    )

    expect(screen.getByPlaceholderText('חיפוש בשיחות')).toHaveAttribute('dir', 'auto')
  })

  it('translates the composer and keeps the key names left-to-right', () => {
    render(
      <I18nProvider initialLocale="he">
        <ChatInput
          value=""
          onChange={vi.fn()}
          onSend={vi.fn()}
          sendingMessage={false}
          answerMode="regular"
          onAnswerModeChange={vi.fn()}
          wsConnectionStatus="connected"
        />
      </I18nProvider>
    )

    expect(screen.getByPlaceholderText('אפשר לשאול כל דבר על מאגר הידע...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'שליחת ההודעה' })).toBeInTheDocument()
    // `Shift+Enter` is a key name, not a phrase: an unisolated one in an RTL
    // line is reordered into `Enter+Shift`, which is a different instruction.
    const shiftEnter = screen.getByText('Shift+Enter')
    // The hint reads as one sentence, with the key names embedded in it.
    expect(shiftEnter.parentElement.textContent).toBe('Enter לשליחה · Shift+Enter לשורה חדשה')
    expect(shiftEnter).toHaveAttribute('dir', 'ltr')
    expect(shiftEnter.className).toContain('unicode-bidi:isolate')
  })

  it('lets the composer follow whatever script the reader types', () => {
    render(
      <I18nProvider initialLocale="he">
        <ChatInput
          value=""
          onChange={vi.fn()}
          onSend={vi.fn()}
          sendingMessage={false}
          answerMode="regular"
          onAnswerModeChange={vi.fn()}
          wsConnectionStatus="connected"
        />
      </I18nProvider>
    )

    expect(screen.getByRole('textbox', { name: 'הודעת צ׳אט' })).toHaveAttribute('dir', 'auto')
  })
})
