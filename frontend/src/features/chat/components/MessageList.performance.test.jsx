/**
 * Long-thread sanity check.
 *
 * The failure this guards against is the one that makes a long conversation
 * feel laggy: appending a streamed message re-rendering — or worse, remounting
 * — every earlier bubble. Node identity is the observable proxy for that, and
 * it stays stable only while the bubbles are memoised and the callbacks handed
 * to them keep their identity across renders.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MessageList from './MessageList'

const THREAD_LENGTH = 200

function buildThread(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: `message-${index}`,
    turnId: `turn-${Math.floor(index / 2)}`,
    sender: index % 2 === 0 ? 'You' : 'Assistant',
    text: `Message body number ${index}`,
    timestamp: '2026-03-17T00:00:00Z',
    isLoading: false,
    metadata: {},
  }))
}

function renderThread(messages, props = {}) {
  return (
    <MessageList
      messages={messages}
      turnsById={{}}
      suggestedPrompts={[]}
      onSuggestedPrompt={props.onSuggestedPrompt || (() => {})}
      onOpenInspector={props.onOpenInspector || (() => {})}
      onAnswerFeedback={props.onAnswerFeedback || (() => {})}
      canInspect={false}
      activityStatus={props.activityStatus ?? null}
    />
  )
}

describe('MessageList long threads', () => {
  it('renders a 200-message thread', () => {
    const messages = buildThread(THREAD_LENGTH)
    render(renderThread(messages))

    expect(screen.getByText('Message body number 0')).toBeInTheDocument()
    expect(screen.getByText(`Message body number ${THREAD_LENGTH - 1}`)).toBeInTheDocument()
  })

  it('keeps existing bubbles mounted when a message is appended', () => {
    const messages = buildThread(THREAD_LENGTH)
    // Stable callbacks are what let the memoised bubbles bail out; ChatTab
    // supplies these from useCallback for exactly this reason.
    const stable = {
      onOpenInspector: vi.fn(),
      onAnswerFeedback: vi.fn(),
      onSuggestedPrompt: vi.fn(),
    }
    const { rerender } = render(renderThread(messages, stable))

    const firstNode = screen.getByText('Message body number 0')
    const midNode = screen.getByText('Message body number 100')

    rerender(renderThread([
      ...messages,
      {
        id: 'message-new',
        turnId: 'turn-new',
        sender: 'Assistant',
        text: 'A freshly streamed answer',
        timestamp: '2026-03-17T00:05:00Z',
        isLoading: false,
        metadata: {},
      },
    ], stable))

    expect(screen.getByText('A freshly streamed answer')).toBeInTheDocument()
    expect(screen.getByText('Message body number 0')).toBe(firstNode)
    expect(screen.getByText('Message body number 100')).toBe(midNode)
  })

  it('shows a real execution stage rather than a fabricated one', () => {
    render(renderThread(buildThread(4), { activityStatus: { node: 'rerank_and_merge', phase: 'started' } }))

    expect(screen.getByText('Reranking…')).toBeInTheDocument()
  })

  it('shows nothing while no turn is running', () => {
    render(renderThread(buildThread(4)))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
