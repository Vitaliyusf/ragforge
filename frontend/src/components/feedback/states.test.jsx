import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import LoadingState from './LoadingState'
import PermissionDeniedState from './PermissionDeniedState'
import StaleNotice from './StaleNotice'

function setReducedMotion(reduced) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: reduced && query === '(prefers-reduced-motion: reduce)',
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
}

describe('LoadingState', () => {
  it('announces itself as busy to assistive technology', () => {
    render(<LoadingState label="Loading files…" />)
    const node = screen.getByRole('status')
    expect(node).toHaveAttribute('aria-busy', 'true')
    expect(node).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('Loading files…')).toBeInTheDocument()
  })

  it('stops spinning under reduced motion', () => {
    setReducedMotion(true)
    const { container } = render(<LoadingState />)
    expect(container.querySelector('svg')).not.toHaveClass('animate-spin')
  })

  it('reserves space so the loaded content does not shift the layout', () => {
    render(<LoadingState minHeight={240} />)
    expect(screen.getByRole('status')).toHaveStyle({ minHeight: '240px' })
  })
})

describe('ErrorState', () => {
  it('is an alert and keeps room for recovery', () => {
    render(
      <ErrorState
        title="Could not load runs"
        description="The eval service did not respond."
        action={<button type="button">Retry</button>}
      />
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('isolates machine detail left-to-right', () => {
    render(<ErrorState detail="req-123" />)
    expect(screen.getByText('req-123')).toHaveAttribute('dir', 'ltr')
  })
})

describe('EmptyState', () => {
  it('is announced and carries no decorative animation', () => {
    const Icon = (props) => <svg data-testid="icon" {...props} />
    const { container } = render(<EmptyState icon={Icon} title="No files uploaded yet" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(container.querySelector('.animate-float')).toBeNull()
  })
})

describe('PermissionDeniedState', () => {
  it('explains the block rather than presenting it as a failure', () => {
    render(<PermissionDeniedState />)
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText(/administrator/i)).toBeInTheDocument()
  })
})

describe('StaleNotice', () => {
  it('defaults to the stale variant with a polite live region', () => {
    render(<StaleNotice />)
    const node = screen.getByRole('status')
    expect(node).toHaveAttribute('aria-live', 'polite')
    expect(node).toHaveAttribute('data-variant', 'stale')
  })

  it('distinguishes partial results from stale ones', () => {
    render(<StaleNotice variant="partial" />)
    expect(screen.getByRole('status')).toHaveAttribute('data-variant', 'partial')
    expect(screen.getByText(/incomplete/i)).toBeInTheDocument()
  })
})
