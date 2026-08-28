/**
 * Hebrew and English travel together in RagForge answers, and the two rules
 * pull against each other: prose must lay out in its own direction, while
 * technical strings must stay left-to-right or the bidi algorithm reorders
 * their punctuation. These tests pin both halves.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MessageList from './MessageList'
import DeveloperInspector from './inspector/DeveloperInspector'

function renderMessages(messages) {
  return render(
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
  )
}

function bubbleOf(text) {
  return screen.getByText(text).closest('[dir]')
}

describe('MessageList bidi', () => {
  it('lays out a Hebrew answer right-to-left', () => {
    renderMessages([{ id: 'm1', sender: 'Assistant', text: 'המסמך מתאר את תהליך האחזור.' }])

    expect(bubbleOf('המסמך מתאר את תהליך האחזור.')).toHaveAttribute('dir', 'rtl')
  })

  it('lets the browser resolve a mixed Hebrew/English message per paragraph', () => {
    renderMessages([{ id: 'm1', sender: 'Assistant', text: 'The model is gpt-4o-mini ואז המסמך.' }])

    expect(bubbleOf('The model is gpt-4o-mini ואז המסמך.')).toHaveAttribute('dir', 'auto')
  })

  it('keeps an English answer left-to-right', () => {
    renderMessages([{ id: 'm1', sender: 'Assistant', text: 'Vector search runs first.' }])

    expect(bubbleOf('Vector search runs first.')).toHaveAttribute('dir', 'ltr')
  })

  it('pins identifiers in the inspector to left-to-right', () => {
    render(
      <DeveloperInspector
        onClose={vi.fn()}
        turn={null}
        message={{
          sender: 'Assistant',
          text: 'תשובה',
          metadata: {
            conversationId: 'chat-1',
            traceId: 'trace-9',
            traceEvents: [{ node: 'rerank_and_merge', latency: 12 }],
          },
        }}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /^Trace$/ }))
    const identifier = screen.getByText('trace-9')
    expect(identifier).toHaveAttribute('dir', 'ltr')
  })

  it('drops zero-UUID placeholders instead of showing them as identifiers', () => {
    render(
      <DeveloperInspector
        onClose={vi.fn()}
        turn={null}
        message={{
          sender: 'Assistant',
          text: 'answer',
          metadata: {
            conversationId: 'chat-1',
            traceId: '00000000-0000-0000-0000-000000000000',
            traceEvents: [{ node: 'rerank_and_merge', latency: 12 }],
          },
        }}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /^Trace$/ }))
    expect(screen.getByText('chat-1')).toBeInTheDocument()
    expect(screen.queryByText('00000000-0000-0000-0000-000000000000')).not.toBeInTheDocument()
  })
})
