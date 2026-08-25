'use client'

import { History, RefreshCw } from 'lucide-react'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import { DataCell, CodeBlock } from '@/components/ui/DataDisplay'

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
        <div className="rounded-2xl border border-border bg-bg-tertiary px-4 py-3 text-[15px] text-text-secondary">
          Loading audit trail...
        </div>
      ) : null}

      {auditState?.error ? (
        <div className="rounded-2xl border border-danger bg-danger-soft px-4 py-3 text-[15px] text-danger">
          {auditState.error}
        </div>
      ) : null}

      {!auditState?.loading && events.length === 0 ? (
        <div className="rounded-2xl border border-border bg-bg-tertiary px-4 py-3 text-[15px] text-text-secondary">
          No audit events found for this file yet.
        </div>
      ) : null}

      {events.length > 0 ? (
        <div className="space-y-3">
          {events.map((event, index) => (
            <div key={event.event_id || `${event.event_type || 'event'}-${event.created_at || index}`} className="rounded-2xl border border-border bg-bg-tertiary/70 p-4">
              <div className="flex flex-wrap items-center gap-2 text-[15px] font-semibold text-text-primary">
                <History size={15} className="text-accent" />
                <span>{event.event_type}</span>
                <span className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs font-medium text-text-secondary">
                  {formatDate(event.created_at)}
                </span>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <DataCell label="From status" value={event.from_status} />
                <DataCell label="To status" value={event.to_status} />
                <DataCell label="Actor" value={event.actor?.display_name} />
                <DataCell label="Reason" value={event.reason} />
                {/* Identifiers that make an audit entry cross-referenceable
                    against the file task and review records it came from. */}
                <DataCell label="Event ID" value={event.event_id} />
                <DataCell label="Task ID" value={event.task_id} />
                {event.review_case_id ? (
                  <DataCell label="Review case ID" value={event.review_case_id} />
                ) : null}
                {event.decision_id ? (
                  <DataCell label="Decision ID" value={event.decision_id} />
                ) : null}
              </div>

              <div className="mt-3 space-y-2">
                <CodeBlock label="Details" content={event.details} />
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


