'use client'

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, FileWarning, Scissors, ShieldCheck, Trash2 } from 'lucide-react'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import TechnicalText from '@/components/ui/TechnicalText'
import { DataCell } from '@/components/ui/DataDisplay'
import { useI18n } from '@/i18n'

// The action keys are the decision values the files API accepts and never
// change with the interface language.
const ACTION_CONFIG = {
  delete_file: {
    labelKey: 'review.action.deleteFile',
    icon: Trash2,
    descriptionKey: 'review.action.deleteFileDescription',
  },
  remove_problematic_text: {
    labelKey: 'review.action.removeText',
    icon: Scissors,
    descriptionKey: 'review.action.removeTextDescription',
  },
  accept_as_is: {
    labelKey: 'review.action.acceptAsIs',
    icon: ShieldCheck,
    descriptionKey: 'review.action.acceptAsIsDescription',
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
  const { t } = useI18n()
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
    if (!reviewCase) return t('review.loading')
    if (!extractedTextHash) return t('review.missingHash')
    if (selectedAction === 'remove_problematic_text' && patchMap.length === 0) {
      return t('review.missingPatchMap')
    }
    return null
  }, [extractedTextHash, patchMap.length, reviewCase, reviewError, selectedAction, t])

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
      title={file ? t('review.titleFor', { name: file.filename }) : t('review.title')}
      variant="drawer"
      size="xl"
    >
      {!reviewCase && !reviewError ? (
        <div className="rounded-2xl border border-border bg-bg-tertiary px-4 py-3 text-[15px] text-text-secondary">
          {t('review.loading')}
        </div>
      ) : null}

      {reviewError ? (
        <div className="rounded-2xl border border-danger bg-danger-soft px-4 py-3 text-[15px] text-danger">
          {reviewError}
        </div>
      ) : null}

      {reviewCase ? (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2">
            <DataCell label={t('review.openedAt')} value={reviewCase.opened_at} />
            {/* Status and decision status are backend enums; the hash is a
                technical value that must not be reordered. */}
            <DataCell label={t('review.status')} value={reviewCase.status} />
            <DataCell label={t('review.decisionStatus')} value={reviewCase.decision_status} />
            <DataCell
              label={t('review.extractedTextHash')}
              value={<TechnicalText>{extractedTextHash}</TechnicalText>}
              mono
            />
          </div>

          <section className="space-y-2 rounded-2xl border border-border p-4">
            <div className="flex items-center gap-2 text-[15px] font-semibold text-text-primary">
              <FileWarning size={16} className="text-warning" />
              {t('review.problemDescription')}
            </div>
            <p dir="auto" className="text-start text-[15px] text-text-secondary">
              {reviewCase.problem_description || t('review.notProvided')}
            </p>
          </section>

          <section className="space-y-2 rounded-2xl border border-border p-4">
            <div className="flex items-center gap-2 text-[15px] font-semibold text-text-primary">
              <AlertTriangle size={16} className="text-danger" />
              {t('review.problematicSnippet')}
            </div>
            {/* The snippet is document text: it keeps its own direction
                rather than the interface's, since a Hebrew guardrail hit
                can occur in an English corpus and the reverse. */}
            <pre dir="auto" className="whitespace-pre-wrap break-words rounded-xl border border-border bg-bg-elevated p-3 text-start text-[15px] text-text-secondary">
              {reviewCase.problematic_text || t('review.notProvided')}
            </pre>
          </section>

          <section className="space-y-2 rounded-2xl border border-border p-4">
            <div className="text-[15px] font-semibold text-text-primary">{t('review.whyProblematic')}</div>
            <p dir="auto" className="text-start text-[15px] text-text-secondary">
              {reviewCase.why_problematic || t('review.notProvided')}
            </p>
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

          <section className="space-y-3 rounded-2xl border border-border p-4">
            <div className="text-[15px] font-semibold text-text-primary">{t('review.allowedActions')}</div>
            <div className="grid gap-3">
              {actions.map((action) => {
                // An action the backend adds but this build has no wording
                // for shows its raw key rather than a guessed translation.
                const config = ACTION_CONFIG[action] || {
                  label: action,
                  icon: ShieldCheck,
                  descriptionKey: 'review.action.genericDescription',
                }
                const Icon = config.icon
                const active = selectedAction === action

                return (
                  <button
                    key={action}
                    type="button"
                    onClick={() => setSelectedAction(action)}
                    className={`rounded-2xl border px-4 py-3 text-start transition ${
                      active
                        ? 'border-accent'
                        : 'border-border bg-bg-elevated hover:border-border-hover hover:bg-bg-secondary'
                    }`}
                  >
                    <div className="flex items-center gap-2 text-[15px] font-semibold text-text-primary">
                      <Icon size={15} className={active ? 'text-accent' : 'text-text-muted'} />
                      {config.labelKey ? t(config.labelKey) : config.label}
                    </div>
                    <p className="mt-1 text-[15px] text-text-secondary">{t(config.descriptionKey)}</p>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="space-y-2 rounded-2xl border border-border p-4">
            <div className="text-[15px] font-semibold text-text-primary">{t('review.patchMapPreview')}</div>
            {patchMap.length > 0 ? (
              <div className="space-y-2">
                {patchMap.map((patch) => (
                  <div key={patch.patch_id || `${patch.start}-${patch.end}`} className="rounded-xl border border-border bg-bg-elevated p-3 text-[13px] text-text-secondary">
                    {/* The patch id and action are API values, so the line
                        that names them stays LTR. */}
                    <div className="font-medium text-text-primary">
                      <TechnicalText>
                        {patch.patch_id || 'patch'} - {patch.action || 'replace'}
                      </TechnicalText>
                    </div>
                    <div className="mt-1">{t('review.range', { start: patch.start, end: patch.end })}</div>
                    <div className="mt-1">
                      {t('review.replacement', {
                        value: patch.replacement || t('review.emptyString'),
                      })}
                    </div>
                    {patch.reason
                      ? <div className="mt-1">{t('review.reason', { value: patch.reason })}</div>
                      : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-bg-elevated px-3 py-2 text-[15px] text-text-secondary">
                {t('review.noPatchMap')}
              </div>
            )}
          </section>

          <section>
            <label className="block">
              <span className="mb-1 block text-[13px] font-medium text-text-muted">{t('review.notes')}</span>
              <input
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder={t('review.notesPlaceholder')}
                dir="auto"
                className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2 text-[15px] text-text-primary outline-hidden transition focus:border-accent focus:ring-2"
              />
            </label>
          </section>

          {helperMessage ? (
            <div className="rounded-2xl border border-warning bg-warning-soft px-4 py-3 text-[15px] text-warning dark:text-warning">
              {helperMessage}
            </div>
          ) : null}

          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              {t('common.close')}
            </Button>
            <Button
              onClick={handleSubmit}
              loading={reviewState === 'decision submitting'}
              disabled={!canSubmit}
            >
              {t('review.submit')}
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}

