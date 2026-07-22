import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TraceDebugPanel from './TraceDebugPanel'

describe('TraceDebugPanel', () => {
  it('renders identifiers, trace timeline, prompts, safety flags, and raw output', async () => {
    render(
      <TraceDebugPanel
        onClose={vi.fn()}
        message={{
          sender: 'Assistant',
          metadata: {
            conversationId: 'chat-1',
            turnId: 'turn-1',
            requestId: 'request-1',
            traceId: 'trace-1',
            mode: 'regular',
            traceEvents: [
              {
                node: 'retriever',
                event: 'completed',
                decision: 'use_docs',
                counters: { hits: 3 },
                latency: 12,
              },
            ],
            statusEvents: [{ type: 'status', data: { phase: 'retrieval' } }],
            answerReview: { verdict: 'pass' },
            debugPayloads: {
              system_prompt: 'system prompt text',
              raw_prompt: 'raw prompt text',
              visible_reasoning_steps: 'reasoning summary',
              raw_input_safety_flags: { level: 'low' },
              raw_output_safety_flags: { level: 'low' },
              raw_output: 'raw output text',
              output_safety_structured_output_candidates: [
                { risk_level: 'medium' },
                { risk_level: 'low' },
              ],
              output_safety_structured_output_selected_index: 1,
              output_safety_structured_output_selection_policy: 'last_valid',
              output_safety_structured_output_extraction_mode: 'multi_payload_last_valid',
              output_safety_raw_output: '{"risk_level":"medium"} {"risk_level":"low"}',
            },
            sources: [{ title: 'Policy doc' }],
            retrievalSummary: { hits: 3 },
          },
        }}
        turn={null}
      />
    )

    expect(screen.getByText(/Trace \/ Debug/i)).toBeInTheDocument()
    expect(screen.getByText(/Conversation ID/i)).toBeInTheDocument()
    expect(screen.getByText('chat-1')).toBeInTheDocument()
    expect(screen.getByText('retriever')).toBeInTheDocument()
    expect(screen.getByText(/Decision: use_docs/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^Prompt$/i }))
    fireEvent.click(await screen.findByRole('button', { name: /System prompt/i }))
    expect(await screen.findByText(/system prompt text/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /User prompt/i }))
    expect(await screen.findByText(/raw prompt text/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Reasoning \/ Rewrite Summary/i }))
    expect(screen.getByText((content) => content.trim() === 'reasoning summary')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Safety Flags/i }))
    expect(screen.getAllByText(/"level": "low"/i).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /Raw Output/i }))
    expect(screen.getByText((content) => content.trim() === 'raw output text')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Structured Output Candidates/i }))
    expect(screen.getByText(/"selected_payload_index": 1/i)).toBeInTheDocument()
  })
})
