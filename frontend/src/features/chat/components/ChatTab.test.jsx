import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatProvider } from '@/features/chat'
import { renderWithProviders } from '@/test/render'
import ChatTab from './ChatTab'
import chatService from '@/features/chat/services/chatService'
import socketService from '@/features/websocket/services/socketService'

// Controllable router so tests can assert URL-driven navigation and set the
// active chat via the pathname (the single source of truth for currentChatId).
const { navState } = vi.hoisted(() => ({
  navState: { pathname: '/chat/chat-1', push: () => {} },
}))

vi.mock('next/navigation', () => ({
  usePathname: () => navState.pathname,
  useRouter: () => ({ push: navState.push }),
}))

vi.mock('@/features/chat/hooks/useChatInit', () => ({
  useChatInit: () => ({
    suggestedPrompts: ['Summarize my documents'],
  }),
}))

// Controllable LLM readiness so tests can drive the "starting" gate. Defaults to
// ready in beforeEach; a dedicated test flips it to exercise the disabled state.
const { llmReadinessState } = vi.hoisted(() => ({
  llmReadinessState: { value: { llmReady: true, llmChecked: true } },
}))

vi.mock('@/features/chat/hooks/useLlmReadiness', () => ({
  useLlmReadiness: () => llmReadinessState.value,
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
    generateTitle: vi.fn(),
    updateChatTitle: vi.fn(),
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
    navState.pathname = '/chat/chat-1'
    navState.push = vi.fn((path) => { navState.pathname = path })
    llmReadinessState.value = { llmReady: true, llmChecked: true }
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
    chatService.generateTitle.mockResolvedValue({ title: 'Generated title' })
    chatService.updateChatTitle.mockResolvedValue({})
  })

  it('handles direct chat streaming, renders answer review, and opens the trace panel', async () => {
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

    // The default surface carries a compact quality state and nothing
    // engineering-facing: no review UUID, no evaluator model slug.
    expect(await screen.findByText(/Grounded . 1 source . Review passed/)).toBeInTheDocument()
    expect(screen.queryByText(/review-1/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/eval-model/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Citation coverage could be stronger/i)).not.toBeInTheDocument()

    await waitFor(() => {
      expect(chatService.addMessage).toHaveBeenCalledTimes(2)
    })

    // Everything withheld above is reachable through the Developer Inspector,
    // where model input and output stay masked until explicitly revealed.
    const inspectorButtons = screen.getAllByLabelText(/Open developer inspector/i)
    await user.click(inspectorButtons[1])

    expect(await screen.findByText(/^Inspector$/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Generation$/ }))
    expect((await screen.findAllByText(/Hidden by default/i)).length).toBeGreaterThan(0)
    expect(screen.queryByText(/system prompt text/i)).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Reveal System prompt/i }))
    expect(await screen.findByText(/system prompt text/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Reveal Raw output/i }))
    expect(screen.getByText((content) => content.trim() === 'raw output text')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Quality$/ }))
    expect(await screen.findByText(/Citation coverage could be stronger/i)).toBeInTheDocument()
    expect(screen.getByText('eval-model')).toBeInTheDocument()
    expect(screen.getByText('review-1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Trace$/ }))
    await user.click(await screen.findByRole('button', { name: /Reveal Structured output candidates/i }))
    expect(screen.getByText(/"selected_payload_index": 1/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Not helpful/i }))
    await waitFor(() => {
      expect(socketService.sendFeedback).toHaveBeenCalledWith(
        'answer_feedback',
        expect.objectContaining({ label: 'not_helpful', rating: 'negative' })
      )
    })
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

  it('disables the composer and shows a notice while the LLM is not available', async () => {
    llmReadinessState.value = { llmReady: false, llmChecked: true }

    renderChatTab()

    expect(screen.getByLabelText(/Chat message/i)).toBeDisabled()
    expect(screen.getByLabelText(/Send message/i)).toBeDisabled()
    expect(await screen.findByText(/isn.t available yet/i)).toBeInTheDocument()
    // Readiness is reported once, in the composer — the header no longer keeps
    // a second copy of the transport state.
    expect(screen.getAllByText(/LLM not available/i).length).toBe(1)
    expect(socketService.askQuestion).not.toHaveBeenCalled()
  })

  it('navigates to the new chat URL when starting a conversation', async () => {
    navState.pathname = '/'
    chatService.getChats.mockResolvedValue({ chats: [] })
    chatService.createChat.mockResolvedValueOnce({ chat_id: 'new-chat-42', title: 'New Chat' })

    const user = userEvent.setup()
    renderChatTab()

    await user.click(screen.getByRole('button', { name: /New chat/i }))

    await waitFor(() => {
      expect(navState.push).toHaveBeenCalledWith('/chat/new-chat-42')
    })
  })

  it('navigates to an existing chat URL when it is selected', async () => {
    navState.pathname = '/'
    chatService.getChats.mockResolvedValue({
      chats: [
        { id: 'chat-1', title: 'First Chat', updated_at: '2026-03-17T00:00:00Z' },
        { id: 'chat-2', title: 'Second Chat', updated_at: '2026-03-17T00:00:00Z' },
      ],
    })

    const user = userEvent.setup()
    renderChatTab()

    await user.click(await screen.findByRole('button', { name: /Select chat: Second Chat/i }))

    expect(navState.push).toHaveBeenCalledWith('/chat/chat-2')
  })

  it('keeps a streaming answer in the chat that requested it when switching windows', async () => {
    navState.pathname = '/chat/A'
    chatService.getChats.mockResolvedValue({
      chats: [
        { id: 'A', title: 'Chat A', updated_at: '2026-03-17T00:00:00Z' },
        { id: 'B', title: 'Chat B', updated_at: '2026-03-17T00:00:00Z' },
      ],
    })
    chatService.getMessages.mockResolvedValue({ messages: [] })
    // The turn streams a token and then stays open (never resolves), so we can
    // observe the in-flight answer as we switch away and back.
    socketService.askQuestion.mockImplementation(async (payload, handlers) => {
      handlers.onToken?.(createEnvelope('token', { text_delta: 'Answer for A' }, {
        conversation_id: payload.conversation_id,
        turn_id: payload.turn_id,
        request_id: payload.request_id,
        trace_id: payload.trace_id,
      }))
      return new Promise(() => {})
    })

    const user = userEvent.setup()
    // A fresh element per render so React re-reads the mocked pathname instead of
    // bailing out on an identical element reference.
    const renderUi = () => (
      <ChatProvider>
        <ChatTab />
      </ChatProvider>
    )
    const { rerender } = renderWithProviders(renderUi())

    await user.type(screen.getByLabelText(/Chat message/i), 'Question in A')
    await user.click(screen.getByLabelText(/Send message/i))
    expect(await screen.findByText('Answer for A')).toBeInTheDocument()

    // Switch to B mid-stream: A's answer must not leak into B's window.
    navState.pathname = '/chat/B'
    rerender(renderUi())
    await waitFor(() => {
      expect(screen.queryByText('Answer for A')).not.toBeInTheDocument()
    })

    // Switch back to A: its in-flight answer is preserved in its own bucket.
    navState.pathname = '/chat/A'
    rerender(renderUi())
    expect(await screen.findByText('Answer for A')).toBeInTheDocument()
  })

  it('auto-titles an untitled chat as soon as the first LLM reply arrives', async () => {
    navState.pathname = '/chat/chat-1'
    chatService.getChats.mockResolvedValue({
      chats: [{ id: 'chat-1', title: 'New Chat', updated_at: '2026-03-17T00:00:00Z' }],
    })
    chatService.generateTitle.mockResolvedValue({ title: 'Rotating signing keys' })
    socketService.askQuestion.mockImplementation(async (payload, handlers) => {
      const done = createEnvelope('done', { final_answer: 'ok' }, {
        conversation_id: payload.conversation_id,
        turn_id: payload.turn_id,
      })
      handlers.onDone?.(done)
      return done
    })

    const user = userEvent.setup()
    renderChatTab()

    await user.type(screen.getByLabelText(/Chat message/i), 'first question')
    await user.click(screen.getByLabelText(/Send message/i))

    await waitFor(() => {
      expect(chatService.generateTitle).toHaveBeenCalledWith('chat-1')
    })
    // The resolved title lands in both the sidebar item and the header.
    expect((await screen.findAllByText('Rotating signing keys')).length).toBeGreaterThan(0)
  })

  it('processes chat exit when the user leaves a chat they used', async () => {
    navState.pathname = '/chat/A'
    chatService.getChats.mockResolvedValue({
      chats: [
        { id: 'A', title: 'New Chat', updated_at: '2026-03-17T00:00:00Z' },
        { id: 'B', title: 'New Chat', updated_at: '2026-03-17T00:00:00Z' },
      ],
    })
    chatService.getMessages.mockResolvedValue({ messages: [] })
    chatService.processChatExit.mockResolvedValue({ headline: 'Handled on leave' })
    socketService.askQuestion.mockImplementation(async (payload, handlers) => {
      const done = createEnvelope('done', { final_answer: 'ok' }, {
        conversation_id: payload.conversation_id,
        turn_id: payload.turn_id,
      })
      handlers.onDone?.(done)
      return done
    })

    const user = userEvent.setup()
    const renderUi = () => (
      <ChatProvider>
        <ChatTab />
      </ChatProvider>
    )
    const { rerender } = renderWithProviders(renderUi())

    await user.type(screen.getByLabelText(/Chat message/i), 'a question in A')
    await user.click(screen.getByLabelText(/Send message/i))
    await waitFor(() => expect(chatService.addMessage).toHaveBeenCalled())

    // Leaving A for B must curate/title A exactly once.
    navState.pathname = '/chat/B'
    rerender(renderUi())

    await waitFor(() => {
      expect(chatService.processChatExit).toHaveBeenCalledWith('A')
    })
  })

  it('recovers chat history after a transient load failure instead of staying blank', async () => {
    navState.pathname = '/chat/A'
    chatService.getChats.mockResolvedValue({
      chats: [
        { id: 'A', title: 'Chat A', updated_at: '2026-03-17T00:00:00Z' },
        { id: 'B', title: 'Chat B', updated_at: '2026-03-17T00:00:00Z' },
      ],
    })
    // First load of A fails; a later load succeeds. The failure must not poison
    // A's bucket into a permanently empty thread.
    chatService.getMessages.mockImplementation((chatId) => {
      if (chatId === 'A' && chatService.getMessages.mock.calls.filter((c) => c[0] === 'A').length === 1) {
        return Promise.reject(new Error('boom'))
      }
      if (chatId === 'A') {
        return Promise.resolve({ messages: [{ id: 'ma', sender: 'Assistant', message: 'Recovered history' }] })
      }
      return Promise.resolve({ messages: [] })
    })

    const user = userEvent.setup()
    const renderUi = () => (
      <ChatProvider>
        <ChatTab />
      </ChatProvider>
    )
    const { rerender } = renderWithProviders(renderUi())

    // Initial load of A failed → thread is blank (no crash).
    await waitFor(() => expect(chatService.getMessages).toHaveBeenCalledWith('A'))
    expect(screen.queryByText('Recovered history')).not.toBeInTheDocument()

    // Leave A, then come back: the load must be retried, not skipped.
    navState.pathname = '/chat/B'
    rerender(renderUi())
    navState.pathname = '/chat/A'
    rerender(renderUi())

    expect(await screen.findByText('Recovered history')).toBeInTheDocument()
  })

  it('renames a chat from the sidebar and shows the new title immediately', async () => {
    navState.pathname = '/chat/chat-1'
    chatService.getChats.mockResolvedValue({
      chats: [{ id: 'chat-1', title: 'Old Title', updated_at: '2026-03-17T00:00:00Z' }],
    })

    const user = userEvent.setup()
    renderChatTab()

    await user.click(await screen.findByRole('button', { name: /Rename Old Title/i }))
    const input = screen.getByLabelText(/Rename Old Title/i)
    await user.clear(input)
    await user.type(input, 'Key rotation notes{Enter}')

    await waitFor(() => {
      expect(chatService.updateChatTitle).toHaveBeenCalledWith('chat-1', 'Key rotation notes')
    })
    expect((await screen.findAllByText('Key rotation notes')).length).toBeGreaterThan(0)
  })

  it('navigates home after deleting the active chat', async () => {
    navState.pathname = '/chat/chat-1'
    chatService.getChats.mockResolvedValue({
      chats: [{ id: 'chat-1', title: 'Doomed Chat', updated_at: '2026-03-17T00:00:00Z' }],
    })

    const user = userEvent.setup()
    renderChatTab()

    await user.click(await screen.findByRole('button', { name: /Delete Doomed Chat/i }))
    await user.click(await screen.findByRole('button', { name: /^Delete$/i }))

    await waitFor(() => {
      expect(navState.push).toHaveBeenCalledWith('/')
    })
  })
})
