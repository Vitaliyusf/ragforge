import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatProvider } from '@/features/chat'
import { renderWithProviders } from '@/test/render'
import ChatTab from './ChatTab'
import chatService from '@/features/chat/services/chatService'
import socketService from '@/features/websocket/services/socketService'

vi.mock('next/navigation', () => ({
  usePathname: () => '/chat/chat-1',
}))

vi.mock('@/features/chat/hooks/useChatInit', () => ({
  useChatInit: () => ({
    suggestedPrompts: ['Summarize my documents'],
  }),
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ isAdmin: true }),
}))

vi.mock('@/features/chat/services/chatService', () => ({
  default: {
    getChats: vi.fn(),
    getMessages: vi.fn(),
    getModels: vi.fn(),
    createChat: vi.fn(),
    addMessage: vi.fn(),
    deleteChat: vi.fn(),
    processChatExit: vi.fn(),
  },
}))

vi.mock('@/features/websocket/services/socketService', () => ({
  default: {
    connect: vi.fn(),
    onStatusChange: vi.fn(),
    askQuestion: vi.fn(),
    sendFeedback: vi.fn(),
  },
}))

function createEnvelope(type, payload, ids = {}) {
  return {
    type,
    request_id: ids.request_id || 'request-1',
    trace_id: ids.trace_id || 'trace-1',
    conversation_id: ids.conversation_id || 'chat-1',
    turn_id: ids.turn_id || 'turn-1',
    timestamp: '2026-03-17T00:00:00Z',
    data: payload,
  }
}

function renderChatTab() {
  return renderWithProviders(
    <ChatProvider>
      <ChatTab />
    </ChatProvider>
  )
}

describe('ChatTab', () => {
  beforeEach(() => {
    socketService.onStatusChange.mockImplementation((callback) => {
      callback('connected', true)
      return () => {}
    })
    socketService.connect.mockResolvedValue({ connected: true })
    socketService.sendFeedback.mockResolvedValue({ sent: true })

    chatService.getChats.mockResolvedValue({
      chats: [{ id: 'chat-1', title: 'Debug Chat', updated_at: '2026-03-17T00:00:00Z' }],
    })
    chatService.getMessages.mockResolvedValue({ messages: [] })
    chatService.getModels.mockResolvedValue({ models: ['gpt-test'] })
    chatService.createChat.mockResolvedValue({ chat_id: 'chat-1', title: 'New Chat' })
    chatService.addMessage.mockResolvedValue({})
    chatService.deleteChat.mockResolvedValue({})
    chatService.processChatExit.mockResolvedValue({})
  })

  it('handles direct chat streaming, renders answer review, opens trace panel, and sends feedback', async () => {
    const answerReview = {
      review_id: 'review-1',
      verdict: 'pass',
      groundedness_score: 0.91,
      completeness_score: 0.84,
      safety_score: 0.98,
      issues: ['Citation coverage could be stronger'],
      revision_applied: true,
      model_name: 'eval-model',
      created_at: '2026-03-17T00:00:00Z',
    }

    socketService.askQuestion.mockImplementation(async (payload, handlers) => {
      const ids = {
        request_id: payload.request_id,
        trace_id: payload.trace_id,
        conversation_id: payload.conversation_id,
        turn_id: payload.turn_id,
      }

      handlers.onStatus?.(createEnvelope('status', {
        node: 'planner',
        phase: 'retrieval',
        message: 'Routing through regular flow',
        progress: 20,
      }, ids))
      handlers.onTrace?.(createEnvelope('trace', {
        node: 'planner',
        event: 'completed',
        decision: 'use_rag',
        counters: { hits: 2 },
        latency: 12,
      }, ids))
      handlers.onToken?.(createEnvelope('token', { text_delta: 'Hello ' }, ids))
      handlers.onToken?.(createEnvelope('token', { text_delta: 'world' }, ids))
      handlers.onAnswerReview?.(createEnvelope('answer_review', answerReview, ids))

      const doneEvent = createEnvelope('done', {
        final_answer: 'Hello world',
        review_summary: answerReview,
        trace_summary: [{
          node: 'planner',
          event: 'completed',
          decision: 'use_rag',
          counters: { hits: 2 },
          latency: 12,
        }],
        safe_debug_payloads: {
          system_prompt: 'system prompt text',
          raw_prompt: 'raw prompt text',
          visible_reasoning_steps: 'Visible reasoning summary',
          raw_input_safety_flags: { risk: 'low' },
          raw_output_safety_flags: { risk: 'low' },
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
        sources: [{ title: 'Policy document' }],
        retrieval_summary: { hits: 2 },
      }, ids)

      handlers.onDone?.(doneEvent)
      return doneEvent
    })

    const user = userEvent.setup()
    renderChatTab()

    await user.type(screen.getByLabelText(/Chat message/i), 'Hello assistant')
    await user.click(screen.getByLabelText(/Send message/i))

    expect(await screen.findByText('Hello world')).toBeInTheDocument()
    expect(socketService.askQuestion).toHaveBeenCalledWith(
      expect.objectContaining({
        question: 'Hello assistant',
        mode: 'regular',
        conversation_id: 'chat-1',
      }),
      expect.any(Object)
    )

    expect(await screen.findByText(/Answer Review/i)).toBeInTheDocument()
    expect(screen.getByText(/Revision applied/i)).toBeInTheDocument()
    expect(screen.getByText(/Citation coverage could be stronger/i)).toBeInTheDocument()
    expect(screen.getByText(/review-1/i)).toBeInTheDocument()
    expect(screen.getByText(/eval-model/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(chatService.addMessage).toHaveBeenCalledTimes(2)
    })

    const debugButtons = screen.getAllByLabelText(/View trace and debug details/i)
    await user.click(debugButtons[1])

    expect(await screen.findByText(/Trace \/ Debug/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Prompt$/i }))
    await user.click(await screen.findByRole('button', { name: /System prompt/i }))
    expect(await screen.findByText(/system prompt text/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Raw Output/i }))
    expect(screen.getByText((content) => content.trim() === 'raw output text')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Structured Output Candidates/i }))
    expect(screen.getByText(/"selected_payload_index": 1/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Helpful' }))
    await user.click(screen.getByRole('button', { name: 'Clear flow' }))

    await waitFor(() => {
      expect(socketService.sendFeedback).toHaveBeenCalledTimes(2)
    })

    expect(socketService.sendFeedback).toHaveBeenCalledWith(
      'answer_feedback',
      expect.objectContaining({
        conversation_id: 'chat-1',
        mode: 'regular',
        label: 'helpful',
        rating: 'positive',
      })
    )
    expect(socketService.sendFeedback).toHaveBeenCalledWith(
      'flow_feedback',
      expect.objectContaining({
        conversation_id: 'chat-1',
        mode: 'regular',
        category: 'flow_clear',
        label: 'clear',
      })
    )
  })

  it('sends extended mode requests', async () => {
    socketService.askQuestion.mockImplementation(async (payload, handlers) => {
      const ids = {
        request_id: payload.request_id,
        trace_id: payload.trace_id,
        conversation_id: payload.conversation_id,
        turn_id: payload.turn_id,
      }

      handlers.onStatus?.(createEnvelope('status', {
        node: 'research',
        phase: 'synthesis',
        message: 'Working through extended flow',
        progress: 42,
      }, ids))

      await new Promise((resolve) => setTimeout(resolve, 25))

      const doneEvent = createEnvelope('done', {
        final_answer: 'Extended answer complete',
      }, ids)

      handlers.onDone?.(doneEvent)
      return doneEvent
    })

    const user = userEvent.setup()
    window.localStorage.setItem('ragforge-chat-mode', 'extended')
    renderChatTab()

    await user.type(screen.getByLabelText(/Chat message/i), 'Run the extended flow')
    await user.click(screen.getByLabelText(/Send message/i))

    expect(socketService.askQuestion).toHaveBeenCalledWith(
      expect.objectContaining({
        question: 'Run the extended flow',
        mode: 'extended',
      }),
      expect.any(Object)
    )

    expect(await screen.findByText(/Extended answer complete/i)).toBeInTheDocument()
  })
})
