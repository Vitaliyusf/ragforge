/** Status, circuit-breaker and service-label lookup tables. */

import { AlertTriangle, CheckCircle2, CircleDot, XCircle } from 'lucide-react'

export const STATUS_CONFIG = {
  healthy:   { iconColor: 'var(--success)', bg: 'var(--success-soft)', border: 'rgba(34,197,94,0.25)',  icon: CheckCircle2,  label: 'Healthy',   badgeVariant: 'success'  },
  degraded:  { iconColor: 'var(--warning)', bg: 'var(--warning-soft)', border: 'rgba(245,158,11,0.25)', icon: AlertTriangle, label: 'Degraded',  badgeVariant: 'warning'  },
  unhealthy: { iconColor: 'var(--danger)',  bg: 'var(--danger-soft)',  border: 'rgba(239,68,68,0.25)',  icon: XCircle,       label: 'Unhealthy', badgeVariant: 'danger'   },
  unknown:   { iconColor: 'var(--fg-soft)', bg: 'var(--surface-hover)',border: 'var(--border)',          icon: CircleDot,     label: 'Unknown',   badgeVariant: 'default'  },
}

export const CB_STATE = {
  closed:    { label: 'Closed',    variant: 'success' },
  open:      { label: 'Open',      variant: 'danger'  },
  half_open: { label: 'Half-Open', variant: 'warning' },
}

export const SERVICE_LABELS = {
  gateway:   'Gateway',
  llm_agent: 'LLM Agent',
  embedding: 'Embedding',
  reranker:  'Reranker',
  rag:       'RAG Orchestrator',
  files:     'File Service',
  vector_db: 'Vector DB',
  memory:    'Memory',
}
