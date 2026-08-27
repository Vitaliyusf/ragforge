/**
 * Chat activity: transitions, not resting values.
 *
 * Chat finishes constantly, so the two behaviours worth pinning are that a
 * success clears itself and that merely opening an old conversation never
 * counts as one.
 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockUseChat } = vi.hoisted(() => ({ mockUseChat: vi.fn() }))
vi.mock('@/features/chat/context/ChatContext', () => ({ useChat: mockUseChat }))

import { ACTIVITY_FEATURES, ACTIVITY_STATES } from './activityModel'
import { ActivityProvider, useActivity, useFeatureActivity } from './ActivityContext'
import ChatActivityBridge, { CHAT_SUCCESS_TTL } from './sources/ChatActivityBridge'

function Probe() {
  const activity = useFeatureActivity(ACTIVITY_FEATURES.CHAT)
  const { acknowledge } = useActivity()
  return (
    <>
      <span data-testid="state">{activity.state}</span>
      <button type="button" onClick={() => acknowledge(ACTIVITY_FEATURES.CHAT)}>
        open chat
      </button>
    </>
  )
}

function renderBridge(chatState) {
  mockUseChat.mockReturnValue({ chatState })
  return render(
    <ActivityProvider>
      <ChatActivityBridge />
      <Probe />
    </ActivityProvider>
  )
}

async function setChatState(view, chatState) {
  mockUseChat.mockReturnValue({ chatState })
  await act(async () => {
    view.rerender(
      <ActivityProvider>
        <ChatActivityBridge />
        <Probe />
      </ActivityProvider>
    )
  })
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('chat activity', () => {
  it('runs while the answer streams', async () => {
    const view = renderBridge('idle')
    await setChatState(view, 'connecting')
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.RUNNING)
    await setChatState(view, 'streaming')
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.RUNNING)
  })

  it('shows a short success and then clears itself', async () => {
    const view = renderBridge('idle')
    await setChatState(view, 'streaming')
    await setChatState(view, 'done')
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.SUCCESS)
    await act(async () => { vi.advanceTimersByTime(CHAT_SUCCESS_TTL + 10) })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.IDLE)
  })

  it('keeps a failure visible until chat is opened', async () => {
    const view = renderBridge('idle')
    await setChatState(view, 'streaming')
    await setChatState(view, 'error')
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.FAILED)
    await act(async () => { vi.advanceTimersByTime(CHAT_SUCCESS_TTL * 4) })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.FAILED)
    await act(async () => { screen.getByText('open chat').click() })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.IDLE)
  })

  it('ignores a conversation that was already finished when it was opened', async () => {
    const view = renderBridge('done')
    await act(async () => {})
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.IDLE)
    await setChatState(view, 'error')
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.IDLE)
  })
})
