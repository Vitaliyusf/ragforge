import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getMemories: vi.fn(),
  createMemory: vi.fn(),
  updateMemory: vi.fn(),
  deleteMemory: vi.fn(),
  notifyError: vi.fn(),
  notifySuccess: vi.fn(),
}))

vi.mock('react-redux', () => ({ useSelector: () => 0 }))
vi.mock('@/features/memory/services/memoryService', () => ({
  default: {
    getMemories: mocks.getMemories,
    createMemory: mocks.createMemory,
    updateMemory: mocks.updateMemory,
    deleteMemory: mocks.deleteMemory,
  },
}))
vi.mock('@/lib/notify', () => ({
  notifyError: mocks.notifyError,
  notifySuccess: mocks.notifySuccess,
}))

import LongTermMemoryTab from './LongTermMemoryTab'
import MemoryCard from './MemoryCard'

const manualMemory = {
  id: 'manual-1',
  content: 'Use concise answers.',
  category: 'user_preference',
  created_at: '2026-09-01T00:00:00Z',
}

beforeEach(() => {
  mocks.getMemories.mockReset()
  mocks.createMemory.mockReset()
  mocks.updateMemory.mockReset()
  mocks.deleteMemory.mockReset()
})

describe('manual Memory CRUD', () => {
  it('shows a created memory only after the canonical reload succeeds', async () => {
    const user = userEvent.setup()
    mocks.getMemories
      .mockResolvedValueOnce({ memories: [] })
      .mockResolvedValueOnce({ memories: [manualMemory] })
    mocks.createMemory.mockResolvedValue({ status: 'success', memory: manualMemory })

    render(<LongTermMemoryTab />)
    await waitFor(() => expect(mocks.getMemories).toHaveBeenCalledTimes(1))
    await user.click(screen.getAllByRole('button', { name: 'Add Memory' })[0])
    await user.type(screen.getByLabelText('Memory content'), manualMemory.content)
    await user.click(screen.getByRole('button', { name: 'Save Memory' }))

    expect(await screen.findByText(manualMemory.content)).toBeInTheDocument()
    expect(mocks.createMemory).toHaveBeenCalledWith(manualMemory.content, 'user_preference')
    expect(mocks.getMemories).toHaveBeenCalledTimes(2)
    expect(mocks.notifySuccess).toHaveBeenCalledWith('Memory saved')
  })

  it('keeps the draft and reports an actionable create failure', async () => {
    const user = userEvent.setup()
    mocks.getMemories.mockResolvedValue({ memories: [] })
    mocks.createMemory.mockRejectedValue(new Error('Service unavailable'))

    render(<LongTermMemoryTab />)
    await waitFor(() => expect(mocks.getMemories).toHaveBeenCalledTimes(1))
    await user.click(screen.getAllByRole('button', { name: 'Add Memory' })[0])
    const input = screen.getByLabelText('Memory content')
    await user.type(input, manualMemory.content)
    await user.click(screen.getByRole('button', { name: 'Save Memory' }))

    await waitFor(() => expect(mocks.notifyError).toHaveBeenCalledWith(
      'Could not save memory',
      expect.objectContaining({ description: expect.stringContaining('draft') }),
    ))
    expect(input).toHaveValue(manualMemory.content)
  })

  it('deletes through confirmation and removes the item after canonical reload', async () => {
    const user = userEvent.setup()
    mocks.getMemories
      .mockResolvedValueOnce({ memories: [manualMemory] })
      .mockResolvedValueOnce({ memories: [] })
    mocks.deleteMemory.mockResolvedValue({ status: 'success' })

    render(<LongTermMemoryTab />)
    expect(await screen.findByText(manualMemory.content)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete memory' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete', exact: true }))

    await waitFor(() => expect(mocks.deleteMemory).toHaveBeenCalledWith(manualMemory.id))
    await waitFor(() => expect(screen.queryByText(manualMemory.content)).not.toBeInTheDocument())
    expect(mocks.notifySuccess).toHaveBeenCalledWith('Memory deleted')
  })

  it('keeps the item visible and reports an actionable delete failure', async () => {
    const user = userEvent.setup()
    mocks.getMemories.mockResolvedValue({ memories: [manualMemory] })
    mocks.deleteMemory.mockRejectedValue(new Error('Service unavailable'))

    render(<LongTermMemoryTab />)
    expect(await screen.findByText(manualMemory.content)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete memory' }))
    await user.click(screen.getByRole('button', { name: 'Delete', exact: true }))

    await waitFor(() => expect(mocks.notifyError).toHaveBeenCalledWith(
      'Delete failed',
      expect.objectContaining({ description: expect.stringContaining('remains visible') }),
    ))
    expect(screen.getByText(manualMemory.content)).toBeInTheDocument()
  })
})

it('labels user insight memories as AI/system managed without destructive actions', () => {
  render(
    <MemoryCard
      memory={{ ...manualMemory, id: 'insight-1', category: 'user_insight' }}
      isDeleting={false}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
    />,
  )

  expect(screen.getByText('Managed by the system')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit memory' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Delete memory' })).not.toBeInTheDocument()
})
