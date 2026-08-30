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

    // Probes are named for what they are. "Live" used to appear here, on the
    // log stream and on the chat composer meaning three different things.
    expect(screen.getByText('Liveness:', { exact: false })).toHaveTextContent('passing')
    expect(screen.getByText('Readiness:', { exact: false })).toHaveTextContent('failing')
    expect(screen.getByText('Live but not ready for traffic')).toBeInTheDocument()
  })

  it('names the service and its status from the shared vocabularies', () => {
    render(<ServiceCard name="rag" info={{ status: 'degraded', live: true, ready: true }} />)

    expect(screen.getByText('RAG Orchestrator')).toBeInTheDocument()
    const status = screen.getByText('Degraded')
    expect(status).toHaveAttribute('data-domain', 'service')
    expect(status).toHaveAttribute('data-state', 'degraded')
  })

  it('says Unknown rather than inventing a health state the backend never sent', () => {
    render(<ServiceCard name="rag" info={{}} />)
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })
})
