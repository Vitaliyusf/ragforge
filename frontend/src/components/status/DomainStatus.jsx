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
import { useI18n } from '@/i18n'

export default function DomainStatus({ domain, state, label, ...props }) {
  const { t } = useI18n()
  const status = describeStatus(domain, state)
  // The taxonomy is pure and carries both the canonical English label and
  // the key; this is the one place the key becomes words on screen.
  return (
    <StatusIndicator
      tone={status.tone}
      label={label ?? t(status.labelKey)}
      data-domain={status.domain}
      data-state={status.state}
      {...props}
    />
  )
}
