/**
 * Answers now carry inline `[1]` citation markers, and the parser leaves them
 * in the text on purpose — tokens stream to this list as they are produced,
 * so stripping markers afterwards would make the finished message differ from
 * what the reader just watched appear.
 *
 * These tests pin the consequence: the markdown renderer must show a marker
 * as readable text, and must not swallow it or turn it into an empty link.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MessageList from './MessageList'

function renderAnswer(text) {
  return render(
    <MessageList
      messages={[{ id: 'message-1', sender: 'Assistant', text }]}
      turnsById={{}}
      suggestedPrompts={[]}
      onSuggestedPrompt={vi.fn()}
      onOpenDebug={vi.fn()}
      onAnswerFeedback={vi.fn()}
      onFlowFeedback={vi.fn()}
      canViewDebug={false}
      extendedProgress={null}
    />
  )
}

describe('MessageList citation markers', () => {
  it('renders a citation marker as visible text', () => {
    renderAnswer('Vector search runs before reranking [1].')

    expect(
      screen.getByText(/Vector search runs before reranking \[1\]\./)
    ).toBeInTheDocument()
  })

  it('keeps consecutive markers legible rather than dropping one', () => {
    renderAnswer('Both passages agree [1][2].')

    expect(screen.getByText(/Both passages agree \[1\]\[2\]\./)).toBeInTheDocument()
  })

  it('does not turn a marker into a link', () => {
    const { container } = renderAnswer('Grounded in the manual [3].')

    expect(container.querySelector('a')).toBeNull()
  })
})
