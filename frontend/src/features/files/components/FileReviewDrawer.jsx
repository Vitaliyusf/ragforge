'use client'

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, FileWarning, Scissors, ShieldCheck, Trash2 } from 'lucide-react'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'

const ACTION_CONFIG = {
  delete_file: {
    label: 'Delete file',
    icon: Trash2,
    description: 'Reject the file and request cleanup.',
  },
  remove_problematic_text: {
    label: 'Remove problematic text',
    icon: Scissors,
    description: 'Use the provided patch map and resume ingestion with sanitized content.',
  },
  accept_as_is: {
    label: 'Accept as-is',
    icon: ShieldCheck,
    description: 'Resume ingestion and keep the original content searchable with risk annotations.',
  },
}

export default function FileReviewDrawer({
  open,
  onOpenChange,
  file,
  reviewCase,
  reviewState,
  reviewError,
  onSubmitDecision,
}) {
  const [selectedAction, setSelectedAction] = useState(null)
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (!open) {
      setSelectedAction(null)
      setNotes('')
    }
  }, [open, reviewCase?.review_case_id, file?.file_id])

  const actions = reviewCase?.allowed_actions || []
  const extractedTextHash = reviewCase?.extracted_text_hash || reviewCase?.based_on_text_hash || null
  const patchMap = reviewCase?.redaction_patch_map || []
  const canSubmit = Boolean(selectedAction) && reviewState !== 'decision submitting' &&
    (selectedAction !== 'remove_problematic_text' || patchMap.length > 0) &&
    Boolean(extractedTextHash)

  const helperMessage = useMemo(() => {
    if (reviewError) return reviewError
    if (!reviewCase) return 'Loading review case...'
    if (!extractedTextHash) {
      return 'The review case response is missing extracted_text_hash, so the frontend cannot submit a compliant decision yet.'
    }
    if (selectedAction === 'remove_problematic_text' && patchMap.length === 0) {
      return 'This review case does not include a patch map for text removal.'
    }
    return null
  }, [extractedTextHash, patchMap.length, reviewCase, reviewError, selectedAction])

  const handleSubmit = async () => {
    if (!selectedAction || !reviewCase || !extractedTextHash) return

    await onSubmitDecision(file.file_id, {
      review_case_id: reviewCase.review_case_id,
      decision: selectedAction,
      based_on_text_hash: extractedTextHash,
      patch_map: selectedAction === 'remove_problematic_text' ? patchMap : undefined,
      notes: notes || undefined,
      metadata: {
        source: 'frontend_admin_review',
      },
    })

    setSelectedAction(null)
    setNotes('')
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={file ? `Review File: ${file.filename}` : 'Review file'}
      variant="drawer"
      size="xl"
    >
      {!reviewCase && !reviewError ? (
        <div className="rounded-2xl border border-border bg-bg-tertiary px-4 py-3 text-sm text-text-secondary">
          Loading review case...
        </div>
      ) : null}

      {reviewError ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
          {reviewError}
        </div>
      ) : null}

      {reviewCase ? (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2">
            <MetaCard label="Opened at" value={reviewCase.opened_at} />
            <MetaCard label="Status" value={reviewCase.status} />
            <MetaCard label="Decision status" value={reviewCase.decision_status} />
            <MetaCard label="Extracted text hash" value={extractedTextHash} />
          </div>

          <section className="space-y-2 rounded-2xl border border-border bg-bg-tertiary/70 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
              <FileWarning size={16} className="text-amber-500" />
              Problem Description
            </div>
            <p className="text-sm text-text-secondary">{reviewCase.problem_description || 'Not provided'}</p>
          </section>

          <section className="space-y-2 rounded-2xl border border-border bg-bg-tertiary/70 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
              <AlertTriangle size={16} className="text-red-500" />
              Problematic Text Snippet
            </div>
            <pre className="whitespace-pre-wrap break-words rounded-xl border border-border bg-bg-elevated p-3 text-sm text-text-secondary">
              {reviewCase.problematic_text || 'Not provided'}
            </pre>
          </section>

          <section className="space-y-2 rounded-2xl border border-border bg-bg-tertiary/70 p-4">
            <div className="text-sm font-semibold text-text-primary">Why Problematic</div>
            <p className="text-sm text-text-secondary">{reviewCase.why_problematic || 'Not provided'}</p>
            {Array.isArray(reviewCase.issue_categories) && reviewCase.issue_categories.length > 0 ? (
              <div className="flex flex-wrap gap-2 pt-1">
                {reviewCase.issue_categories.map((issue, index) => (
                  <Badge key={`${issue.category || 'issue'}-${index}`} variant="warning">
                    {issue.category || issue.title || `issue_${index + 1}`}
                  </Badge>
                ))}
              </div>
            ) : null}
          </section>

          <section className="space-y-3 rounded-2xl border border-border bg-bg-tertiary/70 p-4">
            <div className="text-sm font-semibold text-text-primary">Allowed Actions</div>
            <div className="grid gap-3">
              {actions.map((action) => {
                const config = ACTION_CONFIG[action] || {
                  label: action,
                  icon: ShieldCheck,
                  description: 'Submit this decision for the current review case.',
                }
                const Icon = config.icon
                const active = selectedAction === action

                return (
                  <button
                    key={action}
                    type="button"
                    onClick={() => setSelectedAction(action)}
                    className={`rounded-2xl border px-4 py-3 text-left transition ${
                      active
                        ? 'border-accent bg-accent/10'
                        : 'border-border bg-bg-elevated hover:border-border-hover hover:bg-bg-secondary'
                    }`}
                  >
                    <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                      <Icon size={15} className={active ? 'text-accent' : 'text-text-muted'} />
                      {config.label}
                    </div>
                    <p className="mt-1 text-sm text-text-secondary">{config.description}</p>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="space-y-2 rounded-2xl border border-border bg-bg-tertiary/70 p-4">
            <div className="text-sm font-semibold text-text-primary">Patch Map Preview</div>
            {patchMap.length > 0 ? (
              <div className="space-y-2">
                {patchMap.map((patch) => (
                  <div key={patch.patch_id || `${patch.start}-${patch.end}`} className="rounded-xl border border-border bg-bg-elevated p-3 text-xs text-text-secondary">
                    <div className="font-medium text-text-primary">
                      {patch.patch_id || 'patch'} - {patch.action || 'replace'}
                    </div>
                    <div className="mt-1">Range: {patch.start} - {patch.end}</div>
                    <div className="mt-1">Replacement: {patch.replacement || '(empty string)'}</div>
                    {patch.reason ? <div className="mt-1">Reason: {patch.reason}</div> : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-bg-elevated px-3 py-2 text-sm text-text-secondary">
                No patch map was provided for this review case.
              </div>
            )}
          </section>

          <section>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-text-muted">Notes</span>
              <input
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Optional decision note"
                className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </label>
          </section>

          {helperMessage ? (
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-600 dark:text-amber-400">
              {helperMessage}
            </div>
          ) : null}

          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            <Button
              onClick={handleSubmit}
              loading={reviewState === 'decision submitting'}
              disabled={!canSubmit}
            >
              Submit decision
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}

function MetaCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-border bg-bg-tertiary px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-text-muted">{label}</div>
      <div className="mt-1 break-all text-sm text-text-primary">{value || '-'}</div>
    </div>
  )
}
