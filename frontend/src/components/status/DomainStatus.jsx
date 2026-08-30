'use client'

/**
 * A status rendered from the taxonomy rather than from a hand-written label.
 *
 * Call sites name the domain and hand over whatever their backend said; the
 * canonical label and tone come from `describeStatus`, so a surface cannot
 * quietly invent a sixth word for "it worked" or borrow a service word for a
 * document.
 */

import StatusIndicator from './StatusIndicator'
import { describeStatus } from './statusDomains'

export default function DomainStatus({ domain, state, label, ...props }) {
  const status = describeStatus(domain, state)
  return (
    <StatusIndicator
      tone={status.tone}
      label={label ?? status.label}
      data-domain={status.domain}
      data-state={status.state}
      {...props}
    />
  )
}
