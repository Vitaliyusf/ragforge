/**
 * Files activity: aggregated from the list the app already holds.
 *
 * The bridge must not invent pipeline phases, must count only what the
 * server actually reports, and must not poll while nothing is processing.
 */
import { act, render, screen } from '@testing-library/react'
import { Provider } from 'react-redux'
import { configureStore } from '@reduxjs/toolkit'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/files/services/fileService', () => ({
  default: { getFiles: vi.fn().mockResolvedValue({ files: [] }) },
}))

import fileService from '@/features/files/services/fileService'
import filesReducer, { setFiles } from '@/store/slices/filesSlice'
import { ACTIVITY_FEATURES, ACTIVITY_STATES } from './activityModel'
import { ActivityProvider, useFeatureActivity, useLiveActivitySource } from './ActivityContext'
import FilesActivityBridge, {
  NAV_FILES_POLL_INTERVAL,
  settleFiles,
  summarizeFiles,
} from './sources/FilesActivityBridge'

function Probe() {
  const activity = useFeatureActivity(ACTIVITY_FEATURES.FILES)
  return (
    <>
      <span data-testid="state">{activity.state}</span>
      <span data-testid="count">{activity.count ?? ''}</span>
      <span data-testid="message">{activity.message || ''}</span>
    </>
  )
}

function FakeFilesTab() {
  useLiveActivitySource(ACTIVITY_FEATURES.FILES)
  return null
}

function renderBridge({ page = null } = {}) {
  const store = configureStore({ reducer: { files: filesReducer } })
  const view = render(
    <Provider store={store}>
      <ActivityProvider>
        <FilesActivityBridge />
        {page}
        <Probe />
      </ActivityProvider>
    </Provider>
  )
  return { store, view }
}

const processing = (id) => ({ file_id: id, status: 'processing' })

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('file summaries', () => {
  it('counts only files the server reports as working', () => {
    const { activeIds } = summarizeFiles([
      processing('a'),
      { file_id: 'b', status: 'complete' },
      { file_id: 'c', status: 'started' },
    ])
    expect(activeIds).toEqual(['a', 'c'])
  })

  it('settles a batch to failure ahead of review, and to success otherwise', () => {
    const statuses = new Map([['a', 'error'], ['b', 'awaiting_review'], ['c', 'complete']])
    expect(settleFiles(['a', 'b'], statuses)).toMatchObject({ state: ACTIVITY_STATES.FAILED, count: 1 })
    expect(settleFiles(['b'], statuses)).toMatchObject({ state: ACTIVITY_STATES.WARNING, count: 1 })
    expect(settleFiles(['c'], statuses)).toMatchObject({ state: ACTIVITY_STATES.SUCCESS })
  })
})

describe('files activity', () => {
  it('aggregates one or more working files into a running state with a count', async () => {
    const { store } = renderBridge()
    await act(async () => { store.dispatch(setFiles([processing('a')])) })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.RUNNING)
    expect(screen.getByTestId('count')).toHaveTextContent('1')
    await act(async () => { store.dispatch(setFiles([processing('a'), processing('b')])) })
    expect(screen.getByTestId('count')).toHaveTextContent('2')
    expect(screen.getByTestId('message')).toHaveTextContent('processing 2 files')
  })

  it('transitions to success when the work finishes', async () => {
    const { store } = renderBridge()
    await act(async () => { store.dispatch(setFiles([processing('a')])) })
    await act(async () => { store.dispatch(setFiles([{ file_id: 'a', status: 'complete' }])) })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.SUCCESS)
  })

  it('transitions to failure, with the number of files that failed', async () => {
    const { store } = renderBridge()
    await act(async () => { store.dispatch(setFiles([processing('a'), processing('b')])) })
    await act(async () => {
      store.dispatch(setFiles([{ file_id: 'a', status: 'error' }, { file_id: 'b', status: 'complete' }]))
    })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.FAILED)
    expect(screen.getByTestId('message')).toHaveTextContent('1 file failed')
  })

  it('never polls while nothing is processing', async () => {
    renderBridge()
    await act(async () => { vi.advanceTimersByTime(NAV_FILES_POLL_INTERVAL * 5) })
    expect(fileService.getFiles).not.toHaveBeenCalled()
  })

  it('polls only when work is in flight and no Files surface is mounted', async () => {
    const { store } = renderBridge({ page: <FakeFilesTab /> })
    await act(async () => { store.dispatch(setFiles([processing('a')])) })
    await act(async () => { vi.advanceTimersByTime(NAV_FILES_POLL_INTERVAL * 2) })
    expect(fileService.getFiles).not.toHaveBeenCalled()

    const { store: store2 } = renderBridge()
    await act(async () => { store2.dispatch(setFiles([processing('a')])) })
    await act(async () => { vi.advanceTimersByTime(NAV_FILES_POLL_INTERVAL) })
    expect(fileService.getFiles).toHaveBeenCalledTimes(1)
  })
})
