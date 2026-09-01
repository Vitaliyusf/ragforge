/**
 * The default answer surface.
 *
 * These pin the product promises of CHAT-01: the answer reads as the primary
 * content, sources can be inspected without leaking chunk internals, and
 * feedback is a two-click interaction that asks for detail only when a reader
 * says the answer was wrong.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MessageList from './MessageList'

const SOURCES = [
  {
    chunk_id: 'chunk-abc',
    source_name: 'Retrieval handbook.pdf',
    page: 12,
    chunk_index: 4,
    score: 0.91,
    text_preview: 'Vector search runs before reranking.',
  },
  {
    chunk_id: 'chunk-def',
    source_name: 'Retrieval handbook.pdf',
    page: 13,
    score: 0.72,
    text_preview: 'The reranker keeps the top eight passages.',
  },
  { chunk_id: 'chunk-ghi', source_name: 'Onboarding notes.md' },
]

function renderAnswer(props = {}) {
  return render(
    <MessageList
      messages={[
        {
          id: 'message-1',
          turnId: 'turn-1',
          sender: 'Assistant',
          text: 'Vector search runs first.',
          timestamp: '2026-03-17T10:04:00Z',
          metadata: {
            sources: props.sources ?? SOURCES,
            answerReview: props.review ?? { verdict: 'pass', groundedness_score: 0.88 },
            feedback: props.feedback ?? null,
          },
        },
      ]}
      turnsById={{}}
      suggestedPrompts={[]}
      onSuggestedPrompt={vi.fn()}
      onOpenInspector={vi.fn()}
      onAnswerFeedback={props.onAnswerFeedback || vi.fn()}
      canInspect={false}
      activityStatus={null}
    />
  )
}

describe('answer surface', () => {
  it('summarises quality compactly instead of showing evaluator internals', () => {
    renderAnswer()

    // Three chunks, two documents: the default line speaks of documents.
    expect(screen.getByText('Grounded · Sources: 2 · Review passed')).toBeInTheDocument()
    expect(screen.queryByText(/groundedness_score/i)).not.toBeInTheDocument()
    expect(screen.queryByText('chunk-abc')).not.toBeInTheDocument()
  })

  it('states answerability in words without claiming an abstention decision', () => {
    renderAnswer({ sources: [], review: { verdict: null, groundedness_score: 0 } })

    expect(screen.getByText('No supporting evidence')).toBeInTheDocument()
    expect(screen.queryByText(/abstain/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Decision:/)).not.toBeInTheDocument()
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
  })

  it('agrees with the source chips on how many sources there are', () => {
    renderAnswer()

    // One count, one meaning: several chunks from one document are one source.
    const counts = screen.getAllByText('Sources: 2', { exact: false })
    expect(counts.length).toBeGreaterThan(0)
    expect(screen.queryByText('Sources: 3', { exact: false })).not.toBeInTheDocument()
  })

  it('names sources by document and counts them', () => {
    renderAnswer()

    // Three chunks, two documents: a reader sees documents.
    expect(screen.getByText('Sources: 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retrieval handbook\.pdf/ })).toBeInTheDocument()
  })

  it('opens a source to its passages without exposing chunk internals', () => {
    renderAnswer()

    fireEvent.click(screen.getByRole('button', { name: /Retrieval handbook\.pdf/ }))

    expect(screen.getByText('Vector search runs before reranking.')).toBeInTheDocument()
    expect(screen.getByText('Page 12')).toBeInTheDocument()
    expect(screen.queryByText(/chunk #/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/91/)).not.toBeInTheDocument()
  })

  it('does not offer inspection for a source with nothing readable behind it', () => {
    renderAnswer()

    expect(screen.queryByRole('button', { name: /Onboarding notes\.md/ })).not.toBeInTheDocument()
    expect(screen.getByText('Onboarding notes.md')).toBeInTheDocument()
  })

  it('sends a positive rating immediately and exactly once', () => {
    const onAnswerFeedback = vi.fn()
    renderAnswer({ onAnswerFeedback })

    fireEvent.click(screen.getByRole('button', { name: 'Helpful' }))

    expect(onAnswerFeedback).toHaveBeenCalledTimes(1)
    expect(onAnswerFeedback).toHaveBeenCalledWith('turn-1', { label: 'helpful', rating: 'positive' })
    expect(screen.queryByLabelText(/What was wrong/i)).not.toBeInTheDocument()
  })

  it('stores nothing on the negative click alone', () => {
    const onAnswerFeedback = vi.fn()
    renderAnswer({ onAnswerFeedback })

    fireEvent.click(screen.getByRole('button', { name: 'Not helpful' }))

    // Every answer_feedback event is persisted and feeds the memory threshold,
    // so the negative signal waits for Send or Skip.
    expect(onAnswerFeedback).not.toHaveBeenCalled()
    expect(screen.getByLabelText(/What was wrong/i)).toBeInTheDocument()
  })

  it('sends one negative event when the detail is skipped', () => {
    const onAnswerFeedback = vi.fn()
    renderAnswer({ onAnswerFeedback })

    fireEvent.click(screen.getByRole('button', { name: 'Not helpful' }))
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(onAnswerFeedback).toHaveBeenCalledTimes(1)
    expect(onAnswerFeedback).toHaveBeenCalledWith('turn-1', { label: 'not_helpful', rating: 'negative' })
    expect(screen.queryByLabelText(/What was wrong/i)).not.toBeInTheDocument()
  })

  it('sends one negative event carrying the optional detail', () => {
    const onAnswerFeedback = vi.fn()
    renderAnswer({ onAnswerFeedback })

    fireEvent.click(screen.getByRole('button', { name: 'Not helpful' }))
    const input = screen.getByLabelText(/What was wrong/i)
    fireEvent.change(input, { target: { value: 'It missed the pricing table' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(onAnswerFeedback).toHaveBeenCalledTimes(1)
    expect(onAnswerFeedback).toHaveBeenCalledWith('turn-1', {
      label: 'not_helpful',
      rating: 'negative',
      comment: 'It missed the pricing table',
    })
    expect(screen.queryByLabelText(/What was wrong/i)).not.toBeInTheDocument()
  })

  it('keeps the reader own message out of the answer footer', () => {
    render(
      <MessageList
        messages={[{ id: 'm-user', turnId: 'turn-1', sender: 'You', text: 'How does retrieval work?' }]}
        turnsById={{}}
        suggestedPrompts={[]}
        onSuggestedPrompt={vi.fn()}
        onOpenInspector={vi.fn()}
        onAnswerFeedback={vi.fn()}
        canInspect={false}
        activityStatus={null}
      />
    )

    expect(screen.getByText('How does retrieval work?')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Helpful' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Copy answer' })).not.toBeInTheDocument()
  })
})
