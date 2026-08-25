/**
 * Mount smoke tests for tabs that carry no other coverage.
 *
 * TrainingTab and ModelManagementTab were edited to add delete confirmation,
 * accessible labels and error handling. Neither had a test, and a missing
 * import or bad JSX in either compiles cleanly but throws on mount.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/features/training/hooks/useTraining', () => ({
  useTraining: () => ({
    datasets: [{ dataset_id: 'd1', name: 'set-a', status: 'validated', num_examples: 5 }],
    jobs: [],
    adapters: [{ adapter_id: 'a1', name: 'ad-a', loaded: false }],
    activeJob: null,
    loading: false,
    error: null,
    uploadDataset: vi.fn(),
    deleteDataset: vi.fn(),
    startTraining: vi.fn(),
    cancelJob: vi.fn(),
    deleteAdapter: vi.fn(),
    refresh: vi.fn(),
  }),
}))

vi.mock('@/features/models', () => ({
  modelService: {
    getImplementations: vi.fn().mockResolvedValue({ implementations: [] }),
    getModels: vi.fn().mockResolvedValue({ models: [] }),
    getModelInfo: vi.fn().mockResolvedValue({}),
    getImplementationInfo: vi.fn().mockResolvedValue({}),
    downloadModel: vi.fn().mockResolvedValue({}),
    getDownloadStatus: vi.fn().mockResolvedValue({ status: 'completed' }),
  },
}))

const { default: TrainingTab } = await import('@/features/training/components/TrainingTab')
const { default: ModelManagementTab } = await import('@/features/models/components/ModelManagementTab')

describe('tabs without other coverage mount', () => {
  it('TrainingTab renders and labels its destructive buttons', () => {
    render(<TrainingTab />)
    expect(screen.getByRole('button', { name: /Delete dataset set-a/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Delete adapter ad-a/i })).toBeInTheDocument()
    // Every button must be reachable by name — no unlabelled icon-only controls.
    for (const button of screen.getAllByRole('button')) {
      const name = button.getAttribute('aria-label') || button.textContent.trim()
      expect(name, 'found a button with no accessible name').not.toBe('')
    }
  })

  it('ModelManagementTab renders', () => {
    expect(() => render(<ModelManagementTab />)).not.toThrow()
  })
})
