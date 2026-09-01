/**
 * The chat shell's side-anchored surfaces, in both directions.
 *
 * A drawer that slides in from the wrong edge behind an icon pointing the
 * other way is two mistakes, not one: the reader learns the affordance is
 * unreliable. The mobile history drawer lives on the logical *start* edge and
 * the inspector on the logical *end*, so both swap with the interface while
 * the conversation surface itself does not move.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import ChatTab from './ChatTab'
import { I18nProvider } from '@/i18n'

const chatState = {
  messages: [],
  turnsById: {},
  chats: [],
  currentChatId: null,
  loading: false,
  chatsLoading: false,
  chatsError: null,
  models: [],
  selectedModel: null,
  defaultModel: 'qwen',
  wsConnectionStatus: 'connected',
  answerMode: 'regular',
  sendingMessage: false,
  deletingChatIds: new Set(),
  generatingTitleChatIds: new Set(),
  activityStatus: null,
  selectChat: vi.fn(),
  setSelectedModel: vi.fn(),
  setAnswerMode: vi.fn(),
  createNewChat: vi.fn(),
  sendMessage: vi.fn(),
  sendAnswerFeedback: vi.fn(),
  sendFlowFeedback: vi.fn(),
  renameChat: vi.fn(),
  deleteChat: vi.fn(),
  loadChats: vi.fn(),
}

vi.mock('@/features/chat', () => ({ useChat: () => chatState }))
vi.mock('@/features/auth', () => ({ useAuth: () => ({ isAdmin: false }) }))
vi.mock('@/features/chat/hooks/useChatInit', () => ({
  useChatInit: () => ({ suggestedPrompts: [] }),
}))
vi.mock('@/features/chat/hooks/useLlmReadiness', () => ({
  useLlmReadiness: () => ({ llmReady: true, llmChecked: true }),
}))

function renderChat(locale) {
  return render(
    <I18nProvider initialLocale={locale}>
      <ChatTab />
    </I18nProvider>
  )
}

/** The drawer is the only fixed, full-height panel in the tree. */
const drawer = () => document.querySelector('aside.fixed')

beforeEach(() => {
  vi.clearAllMocks()
})

describe('mobile chat history drawer', () => {
  it('is anchored to the logical start edge, so it mirrors with the shell', async () => {
    const user = userEvent.setup()
    renderChat('he')

    await user.click(screen.getByRole('button', { name: 'פתיחה או סגירה של היסטוריית השיחות' }))

    // `start-0` and `border-e` are logical: the same markup puts the drawer on
    // the left in English and the right in Hebrew, with its border on the
    // edge that faces the conversation in both.
    expect(drawer().className).toContain('start-0')
    expect(drawer().className).toContain('border-e')
    expect(drawer().className).not.toContain('left-0')
  })

  it('opens under a Hebrew accessible name and closes under another', async () => {
    const user = userEvent.setup()
    renderChat('he')

    await user.click(screen.getByRole('button', { name: 'פתיחה או סגירה של היסטוריית השיחות' }))
    expect(screen.getByText('סביבת הצ׳אט')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'סגירת חלונית היסטוריית השיחות' })
    ).toBeInTheDocument()
  })

  it('keeps the English shell on its original edge', async () => {
    const user = userEvent.setup()
    renderChat('en')

    await user.click(screen.getByRole('button', { name: 'Toggle chat history' }))
    expect(drawer().className).toContain('start-0')
    expect(screen.getByText('Chat workspace')).toBeInTheDocument()
  })
})

describe('chat header copy', () => {
  it('reads in Hebrew, with the empty-thread subtitle translated', () => {
    renderChat('he')
    expect(screen.getByRole('heading', { name: 'שיחה חדשה' })).toBeInTheDocument()
    expect(screen.getByText('אפשר לשאול כל דבר על מאגר הידע')).toBeInTheDocument()
  })

  it('counts messages with a labelled count rather than a plural', () => {
    chatState.messages = [
      { id: 'm1', sender: 'You', text: 'שלום' },
      { id: 'm2', sender: 'Assistant', text: 'שלום גם לך' },
    ]
    renderChat('he')
    expect(screen.getByText('הודעות בשיחה: 2')).toBeInTheDocument()
    chatState.messages = []
  })
})
