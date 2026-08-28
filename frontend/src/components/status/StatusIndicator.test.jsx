import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusIndicator from './StatusIndicator'
import { STATUS_TONE, resolveToneName } from './statusTone'

function setReducedMotion(reduced) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: reduced && query === '(prefers-reduced-motion: reduce)',
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
}

describe('statusTone', () => {
  it('gives every tone a non-colour cue', () => {
    for (const [name, tone] of Object.entries(STATUS_TONE)) {
      expect(tone.icon, `${name} has no icon`).toBeTruthy()
    }
  })

  it('resolves legacy variant names onto tones', () => {
    expect(resolveToneName('error')).toBe('danger')
    expect(resolveToneName('default')).toBe('neutral')
    expect(resolveToneName('accent')).toBe('live')
    expect(resolveToneName('processing')).toBe('live')
  })

  it('falls back to neutral for an unknown name', () => {
    expect(resolveToneName('nonsense')).toBe('neutral')
    expect(resolveToneName(undefined)).toBe('neutral')
  })

  it('marks only the live tone as continuously animating', () => {
    const live = Object.entries(STATUS_TONE).filter(([, t]) => t.live).map(([n]) => n)
    expect(live).toEqual(['live'])
  })
})

describe('StatusIndicator', () => {
  beforeEach(() => setReducedMotion(false))

  it('renders the label as text alongside the icon', () => {
    const { container } = render(<StatusIndicator tone="success" label="Complete" />)
    expect(screen.getByText('Complete')).toBeInTheDocument()
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('keeps an accessible name when the label is visually hidden', () => {
    render(<StatusIndicator tone="danger" label="Failed" iconOnly />)
    const node = screen.getByRole('status')
    expect(node).toHaveAccessibleName('Failed')
    expect(node).not.toHaveTextContent('Failed')
  })

  it('exposes the resolved tone so status is never colour-only', () => {
    render(<StatusIndicator tone="error" label="Broken" />)
    expect(screen.getByRole('status')).toHaveAttribute('data-tone', 'danger')
  })

  it('animates the live tone', () => {
    const { container } = render(<StatusIndicator tone="live" label="Running" />)
    expect(container.querySelector('svg')).toHaveClass('animate-spin')
  })

  it('does not animate the live tone under reduced motion', () => {
    setReducedMotion(true)
    const { container } = render(<StatusIndicator tone="live" label="Running" />)
    expect(container.querySelector('svg')).not.toHaveClass('animate-spin')
  })

  it('never animates a terminal tone', () => {
    const { container } = render(<StatusIndicator tone="success" label="Complete" />)
    expect(container.querySelector('svg')).not.toHaveClass('animate-spin')
  })
})
