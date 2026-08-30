/**
 * Status and circuit-breaker lookup tables for the health surfaces.
 *
 * Service names are not defined here any more: they live in the one
 * terminology module the metrics and log surfaces read from too, because a
 * service that was "RAG Orchestrator" on one screen and "Rag" on the next was
 * two names for one thing.
 */

import { AlertTriangle, CheckCircle2, CircleDot, XCircle } from 'lucide-react'
import { SERVICE_LABELS } from '@/lib/terminology'

/**
 * Card chrome per service status — accent colours and the icon on the card
 * itself. The words and the badge tone come from the service status domain;
 * this table no longer carries a second copy of them.
 */
export const STATUS_CONFIG = {
  healthy:   { iconColor: 'var(--success)', bg: 'var(--success-soft)', border: 'rgba(34,197,94,0.25)',  icon: CheckCircle2  },
  degraded:  { iconColor: 'var(--warning)', bg: 'var(--warning-soft)', border: 'rgba(245,158,11,0.25)', icon: AlertTriangle },
  unhealthy: { iconColor: 'var(--danger)',  bg: 'var(--danger-soft)',  border: 'rgba(239,68,68,0.25)',  icon: XCircle       },
  unknown:   { iconColor: 'var(--fg-soft)', bg: 'var(--surface-hover)',border: 'var(--border)',         icon: CircleDot     },
}

export const CB_STATE = {
  closed:    { label: 'Closed',    variant: 'success' },
  open:      { label: 'Open',      variant: 'danger'  },
  half_open: { label: 'Half-Open', variant: 'warning' },
}

export { SERVICE_LABELS }
