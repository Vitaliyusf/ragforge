import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import ErrorBoundary from './ErrorBoundary'

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

function Boom() {
  throw Object.assign(new Error('structured failure'), {
    code: 'INTERNAL_ERROR',
    request_id: 'req-123',
  })
}

describe('ErrorBoundary', () => {
  it('renders structured error metadata', () => {
    render(
      <ErrorBoundary name="Chat">
        <Boom />
      </ErrorBoundary>
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText(/structured failure/i)).toBeInTheDocument()
    expect(screen.getByText(/code: INTERNAL_ERROR/i)).toBeInTheDocument()
    expect(screen.getByText(/request: req-123/i)).toBeInTheDocument()
  })
})
