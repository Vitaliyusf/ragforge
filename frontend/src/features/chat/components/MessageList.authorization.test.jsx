import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MessageList from './MessageList'


describe('MessageList authorization', () => {
  it('does not render trace or prompt controls for a regular user', () => {
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
        onOpenDebug={vi.fn()}
        onAnswerFeedback={vi.fn()}
        onFlowFeedback={vi.fn()}
        canViewDebug={false}
        extendedProgress={null}
      />
    )

    expect(screen.getByText('Public answer')).toBeInTheDocument()
    expect(screen.queryByLabelText(/View trace and debug details/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show full prompt/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/private system prompt/i)).not.toBeInTheDocument()
  })
})
