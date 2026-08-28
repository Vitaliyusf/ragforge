import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MessageList from './MessageList'


describe('MessageList authorization', () => {
  it('does not render inspector or prompt content for a regular user', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'message-1',
            sender: 'Assistant',
            text: 'Public answer',
            metadata: {
              debugPayloads: {
                system_prompt: 'private system prompt',
                raw_prompt: 'private raw prompt',
              },
            },
          },
        ]}
        turnsById={{}}
        suggestedPrompts={[]}
        onSuggestedPrompt={vi.fn()}
        onOpenInspector={vi.fn()}
        onAnswerFeedback={vi.fn()}
        canInspect={false}
        activityStatus={null}
      />
    )

    expect(screen.getByText('Public answer')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Open developer inspector/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/private system prompt/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/private raw prompt/i)).not.toBeInTheDocument()
  })

  it('keeps the full prompt out of the default answer surface even for an admin', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'message-1',
            sender: 'Assistant',
            text: 'Admin answer',
            metadata: {
              debugPayloads: {
                system_prompt: 'private system prompt',
                raw_prompt: 'private raw prompt',
              },
            },
          },
        ]}
        turnsById={{}}
        suggestedPrompts={[]}
        onSuggestedPrompt={vi.fn()}
        onOpenInspector={vi.fn()}
        onAnswerFeedback={vi.fn()}
        canInspect
        activityStatus={null}
      />
    )

    expect(screen.getByLabelText(/Open developer inspector/i)).toBeInTheDocument()
    expect(screen.queryByText(/private system prompt/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show full prompt/i })).not.toBeInTheDocument()
  })
})
