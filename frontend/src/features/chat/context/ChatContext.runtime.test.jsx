/**
 * Runtime-architecture tests for `ChatProvider` (REACT-19-01).
 *
 * Two behaviours changed shape here and are worth pinning:
 *
 * 1. The model list is fetched once per mount. `loadModels` used to depend on
 *    `selectedModel` purely to seed a default, so the Effect that called it
 *    re-ran and refetched `/models` every time the user picked a model.
 * 2. `currentChatId` is derived from the pathname during render rather than
 *    mirrored into state by an Effect, and history is still loaded exactly
 *    once per conversation.
 */
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Provider } from 'react-redux'
import { createTestStore } from '@/test/render'

const { navState } = vi.hoisted(() => ({
  navState: { pathname: '/chat/chat-1', push: () => {} },
}))

vi.mock('next/navigation', () => ({
  usePathname: () => navState.pathname,
  useRouter: () => ({ push: navState.push }),
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

import chatService from '@/features/chat/services/chatService'
import socketService from '@/features/websocket/services/socketService'
import { ChatProvider, useChat } from './ChatContext'

function Probe() {
  const { currentChatId, models, selectedModel, setSelectedModel } = useChat()
  return (
    <div>
      <span data-testid="chat-id">{currentChatId ?? 'none'}</span>
      <span data-testid="selected-model">{selectedModel ?? 'none'}</span>
      <button type="button" onClick={() => setSelectedModel(models[1])}>
        pick second model
      </button>
    </div>
  )
}

function renderProvider() {
  return render(
    <Provider store={createTestStore()}>
      <ChatProvider>
        <Probe />
      </ChatProvider>
    </Provider>
  )
}

describe('ChatProvider runtime', () => {
  beforeEach(() => {
    navState.pathname = '/chat/chat-1'
    navState.push = vi.fn((path) => { navState.pathname = path })
    socketService.onStatusChange.mockImplementation(() => () => {})
    socketService.connect.mockResolvedValue({ connected: true })
    chatService.getChats.mockResolvedValue({ chats: [] })
    chatService.getMessages.mockResolvedValue({ messages: [] })
    chatService.getModels.mockResolvedValue({ models: ['model-a', 'model-b'] })
  })

  it('fetches the model list once and does not refetch when the selection changes', async () => {
    renderProvider()

    await waitFor(() => expect(screen.getByTestId('selected-model')).toHaveTextContent('model-a'))
    expect(chatService.getModels).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: /pick second model/i }))

    await waitFor(() => expect(screen.getByTestId('selected-model')).toHaveTextContent('model-b'))
    expect(chatService.getModels).toHaveBeenCalledTimes(1)
  })

  it('derives the active chat from the pathname on the first render', async () => {
    renderProvider()

    // No Effect round-trip: the id is right in the very first paint.
    expect(screen.getByTestId('chat-id')).toHaveTextContent('chat-1')
    await waitFor(() => expect(chatService.getMessages).toHaveBeenCalledWith('chat-1'))
  })

  it('loads history once per conversation and again after navigating', async () => {
    const { rerender } = renderProvider()
    await waitFor(() => expect(chatService.getMessages).toHaveBeenCalledTimes(1))

    // A re-render with the same pathname must not refetch a loaded bucket.
    await act(async () => {
      rerender(
        <Provider store={createTestStore()}>
          <ChatProvider>
            <Probe />
          </ChatProvider>
        </Provider>
      )
    })
    expect(chatService.getMessages).toHaveBeenCalledTimes(1)

    navState.pathname = '/chat/chat-2'
    await act(async () => {
      rerender(
        <Provider store={createTestStore()}>
          <ChatProvider>
            <Probe />
          </ChatProvider>
        </Provider>
      )
    })

    expect(screen.getByTestId('chat-id')).toHaveTextContent('chat-2')
    await waitFor(() => expect(chatService.getMessages).toHaveBeenCalledTimes(2))
    expect(chatService.getMessages).toHaveBeenLastCalledWith('chat-2')
  })
})
