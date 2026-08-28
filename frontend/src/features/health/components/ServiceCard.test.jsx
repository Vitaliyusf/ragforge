import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ServiceCard from './ServiceCard'


describe('ServiceCard', () => {
  it('distinguishes a live service that is not ready', () => {
    render(<ServiceCard name="rag" info={{
      status: 'degraded',
      live: true,
      ready: false,
      message: 'Live but not ready for traffic',
    }} />)

    expect(screen.getByText('Live:', { exact: false })).toHaveTextContent('yes')
    expect(screen.getByText('Ready:', { exact: false })).toHaveTextContent('no')
    expect(screen.getByText('Live but not ready for traffic')).toBeInTheDocument()
  })
})
