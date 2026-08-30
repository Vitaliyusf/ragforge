'use client'

import { AlertTriangle, Loader2, ShieldAlert, Trash2 } from 'lucide-react'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import { DataRow } from '@/components/ui/DataDisplay'
import { formatFileSize } from '@/lib/formatting/bytes'
import { formatAbsoluteDateTime } from '@/lib/formatting/datetime'
import { ltrIsolateProps } from '@/lib/accessibility/direction'
import DeepLink from '@/components/observability/DeepLink'
import { logsLinkForCorrelation } from '@/lib/observability/deepLinks'
import {
  DOCUMENT_STATUSES,
  describeFailure,
  getDocumentStatus,
  getDocumentType,
  getPipelineStages,
  summarizePipeline,
} from '../documentModel'
import { DocumentPipelineCell, DocumentStatusBadge } from './DocumentStatus'

/** The services that touch a file between upload and index. */
const INGESTION_LOG_SERVICES = ['files', 'embedding', 'vector_db']

function Section({ title, children }) {
  return (
    <section className="border-t border-border pt-4 first:border-t-0 first:pt-0">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-fg-soft">{title}</h3>
      {children}
    </section>
  )
}

const STAGE_STATE_TEXT = {
  done: { label: 'Done', color: 'var(--success)' },
  running: { label: 'Running', color: 'var(--status-live)' },
  failed: { label: 'Failed', color: 'var(--danger)' },
  skipped: { label: 'Skipped', color: 'var(--fg-soft)' },
  paused: { label: 'Paused', color: 'var(--warning)' },
  waiting: { label: 'Waiting', color: 'var(--fg-soft)' },
}

/** Chunk counts are only ever read off a real chunking event. */
function findChunkCount(events) {
  for (const event of events || []) {
    const count = event?.details?.chunk_count
    if (Number.isFinite(count)) return count
  }
  return null
}

/**
 * The document detail surface.
 *
 * Every section is conditional on data that actually exists: there is no
 * Retrieval section because the files API exposes no retrieval history, and
 * no stage durations because none are recorded per stage. Activity is the one
 * thing fetched on open — list-level data is never re-requested here.
 */
export default function DocumentDrawer({
  open,
  onOpenChange,
  file,
  activity,
  onLoadMoreActivity,
  onDelete,
  onReview,
  isDeleting,
  requiresReview,
}) {
  if (!file) return null

  const status = getDocumentStatus(file)
  const stages = getPipelineStages(file)
  const pipeline = summarizePipeline(file)
  const events = activity?.events || []
  const failure = describeFailure(file, events)
  const chunkCount = findChunkCount(events)
  const keywords = Array.isArray(file.metadata?.keywords) ? file.metadata.keywords : []
  const summary = typeof file.summary === 'string' ? file.summary.trim() : ''

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      variant="drawer"
      size="lg"
      title={file.filename || 'Document'}
    >
      <div className="space-y-5">
        {failure ? (
          <div className="rounded-xl border border-danger bg-danger-soft p-4">
            <div className="flex items-start gap-2">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-[15px] font-semibold text-danger">{failure.title}</p>
                <p className="mt-1 text-[13px] text-fg-muted">
                  {failure.reason || 'No failure detail was recorded for this document.'}
                </p>
                <p className="text-[13px] text-fg-muted">{failure.impact}</p>
                {/* No retry button: the files service exposes no operation
                    that restarts a finished ingestion run, so the only honest
                    next steps are the ones below. */}
                <ul className="mt-3 space-y-1 text-[13px] text-fg-muted">
                  <li>Review the Activity section for failure details.</li>
                  <li>Retry is not currently available for this ingestion run.</li>
                  <li>Upload the document again after correcting the issue.</li>
                </ul>
              </div>
            </div>
          </div>
        ) : null}

        <Section title="Overview">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <DocumentStatusBadge file={file} size="md" />
            <DocumentPipelineCell file={file} />
          </div>
          <div className="space-y-1.5">
            <DataRow label="Type" value={getDocumentType(file) || file.content_type || '—'} />
            <DataRow label="Size" value={file.size ? formatFileSize(file.size) : '—'} />
            {file.owner_display_name || file.owner_email ? (
              <DataRow label="Owner" value={file.owner_display_name || file.owner_email} />
            ) : null}
            <DataRow label="Uploaded" value={formatAbsoluteDateTime(file.created_at) || '—'} />
            <DataRow
              label={status === DOCUMENT_STATUSES.READY ? 'Indexed' : 'Updated'}
              value={formatAbsoluteDateTime(file.updated_at) || '—'}
            />
            {file.review_status && file.review_status !== 'not_required' ? (
              <DataRow label="Review" value={String(file.review_status).replace(/_/g, ' ')} />
            ) : null}
            <DataRow label="Document ID" value={file.file_id} mono />
            {file.current_task_id ? (
              <DataRow label="Task ID" value={file.current_task_id} mono />
            ) : null}
          </div>
        </Section>

        {stages.length > 0 ? (
          <Section title="Pipeline">
            <ol className="space-y-1">
              {stages.map((stage) => {
                const presentation = STAGE_STATE_TEXT[stage.state] ?? STAGE_STATE_TEXT.waiting
                const current = stage.key === pipeline.stageKey
                return (
                  <li
                    key={stage.key}
                    className={`flex items-center justify-between rounded-lg px-2 py-1.5 text-[13px] ${
                      current ? 'bg-surface-hover' : ''
                    }`}
                  >
                    <span className={current ? 'font-medium text-fg' : 'text-fg-muted'}>{stage.label}</span>
                    <span style={{ color: presentation.color }}>{presentation.label}</span>
                  </li>
                )
              })}
            </ol>
            <p className="mt-2 text-xs text-fg-soft">
              Per-stage durations are not recorded by the ingestion service.
            </p>
          </Section>
        ) : null}

        {chunkCount != null ? (
          <Section title="Chunks">
            <DataRow label="Chunks created" value={String(chunkCount)} />
          </Section>
        ) : null}

        {summary || keywords.length > 0 ? (
          <Section title="Content">
            {summary ? (
              <p dir="auto" className="mb-2 line-clamp-6 text-[13px] leading-relaxed text-fg-muted">
                {summary}
              </p>
            ) : null}
            {keywords.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {keywords.slice(0, 12).map((keyword) => (
                  <span
                    key={String(keyword)}
                    className="rounded-md bg-surface-hover px-2 py-0.5 text-xs text-fg-muted"
                    dir="auto"
                  >
                    {String(keyword)}
                  </span>
                ))}
              </div>
            ) : null}
          </Section>
        ) : null}

        <Section title="Activity">
          {activity?.loading ? (
            <p className="flex items-center gap-2 text-[13px] text-fg-soft">
              <Loader2 size={13} className="animate-spin" /> Loading activity…
            </p>
          ) : null}
          {activity?.error ? (
            <p className="text-[13px] text-danger">{activity.error}</p>
          ) : null}
          {!activity?.loading && !activity?.error && events.length === 0 ? (
            <p className="text-[13px] text-fg-soft">No ingestion events recorded yet.</p>
          ) : null}
          {events.length > 0 ? (
            <ol className="space-y-2.5">
              {events.map((event, index) => (
                <li
                  key={event.event_id || `${event.event_type}-${index}`}
                  className="border-s border-border ps-3"
                >
                  <p className="text-[13px] font-medium text-fg">
                    {String(event.event_type || 'event').replace(/_/g, ' ')}
                  </p>
                  <p className="text-xs text-fg-soft">
                    {formatAbsoluteDateTime(event.created_at) || '—'}
                    {event.actor?.display_name ? ` · ${event.actor.display_name}` : ''}
                  </p>
                  {event.reason ? (
                    <p className="mt-0.5 text-[13px] text-fg-muted">{event.reason}</p>
                  ) : null}
                  {event.task_id ? (
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-xs text-fg-soft" {...ltrIsolateProps()}>
                        {event.task_id}
                      </span>
                      {/* The id the ingestion services logged this stage
                          under — the only trail an ingestion failure leaves
                          outside this drawer. */}
                      <DeepLink
                        link={logsLinkForCorrelation({
                          id: event.task_id,
                          kindLabel: 'ingestion task',
                          services: INGESTION_LOG_SERVICES,
                        })}
                      />
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : null}
          {activity?.nextCursor ? (
            <div className="pt-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onLoadMoreActivity(file.file_id)}
                loading={activity.loadingMore}
              >
                Load more
              </Button>
            </div>
          ) : null}
        </Section>

        <Section title="Actions">
          <div className="flex flex-wrap gap-2">
            {requiresReview ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onReview(file.file_id)}
                leftIcon={<ShieldAlert size={13} />}
              >
                Open review
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="danger"
              onClick={() => onDelete(file)}
              loading={isDeleting}
              leftIcon={<Trash2 size={13} />}
            >
              Delete
            </Button>
          </div>
          <p className="mt-2 text-xs text-fg-soft">
            Re-ingesting an existing document is not an operation the files service supports;
            upload the document again to run the pipeline afresh.
          </p>
        </Section>
      </div>
    </Modal>
  )
}
