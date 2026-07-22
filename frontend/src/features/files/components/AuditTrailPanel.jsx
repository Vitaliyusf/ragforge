'use client'

import { History, RefreshCw } from 'lucide-react'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'

function formatDate(value) {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

export default function AuditTrailPanel({
  open,
  onOpenChange,
  file,
  auditState,
  onLoadMore,
}) {
  const events = auditState?.events || []

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={file ? `Audit Trail: ${file.filename}` : 'Audit trail'}
      variant="drawer"
      size="xl"
    >
      {auditState?.loading ? (
        <div className="rounded-2xl border border-border bg-bg-tertiary px-4 py-3 text-sm text-text-secondary">
          Loading audit trail...
        </div>
      ) : null}

      {auditState?.error ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
          {auditState.error}
        </div>
      ) : null}

      {!auditState?.loading && events.length === 0 ? (
        <div className="rounded-2xl border border-border bg-bg-tertiary px-4 py-3 text-sm text-text-secondary">
          No audit events found for this file yet.
        </div>
      ) : null}

      {events.length > 0 ? (
        <div className="space-y-3">
          {events.map((event, index) => (
            <div key={event.event_id || `${event.event_type || 'event'}-${event.created_at || index}`} className="rounded-2xl border border-border bg-bg-tertiary/70 p-4">
              <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-text-primary">
                <History size={15} className="text-accent" />
                <span>{event.event_type}</span>
                <span className="rounded-full bg-bg-elevated px-2 py-0.5 text-[11px] font-medium text-text-secondary">
                  {formatDate(event.created_at)}
                </span>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <AuditMeta label="From status" value={event.from_status} />
                <AuditMeta label="To status" value={event.to_status} />
                <AuditMeta label="Actor" value={event.actor?.display_name} />
                <AuditMeta label="Reason" value={event.reason} />
              </div>

              <div className="mt-3 space-y-2">
                <AuditBlock label="Details" value={event.details} />
              </div>
            </div>
          ))}

          {auditState?.nextCursor ? (
            <div className="flex justify-center pt-2">
              <Button
                variant="secondary"
                onClick={() => onLoadMore(file.file_id)}
                loading={auditState.loadingMore}
                leftIcon={<RefreshCw size={14} />}
              >
                Load more
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </Modal>
  )
}

function AuditMeta({ label, value }) {
  return (
    <div className="rounded-xl border border-border bg-bg-elevated px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-text-muted">{label}</div>
      <div className="mt-1 break-all text-sm text-text-primary">{value || '-'}</div>
    </div>
  )
}

function AuditBlock({ label, value }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-text-muted">{label}</div>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-bg-elevated p-3 text-xs text-text-secondary">
        {value ? JSON.stringify(value, null, 2) : 'Not available'}
      </pre>
    </div>
  )
}
