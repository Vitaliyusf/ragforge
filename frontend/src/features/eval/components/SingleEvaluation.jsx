'use client'

import { useState } from 'react'
import { Play } from 'lucide-react'
import Button from '@/components/ui/Button'
import { ConfirmModal } from '@/components/ui/Modal'
import Select, { SelectItem } from '@/components/ui/Select'
import {
  EVAL_MODE_HELP_KEYS,
  EVAL_MODE_LABEL_KEYS,
  UNPRICED_MODEL_NOTE_KEY,
  formatCost,
  formatCount,
} from '@/features/metrics/components/metricsConfig'
import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'
import { useI18n } from '@/i18n'

/**
 * The ad-hoc eval, kept and demoted.
 *
 * It is a different thing from a benchmark — one retrieval or end-to-end
 * pass, no phases, no archive — and it is still the fastest way to see
 * whether a retrieval change moved recall at all. Demoting it to a
 * disclosure removes the second primary button without removing the run.
 */
export default function SingleEvaluation({
  dataset,
  datasetId,
  run,
  busy,
  running,
  onStart,
  onEstimate,
}) {
  const { t } = useI18n()
  const [mode, setMode] = useState('retrieval')
  // The estimate doubles as the confirmation gate: an end-to-end run cannot
  // start until one has been fetched and shown.
  const [estimate, setEstimate] = useState(null)
  const [estimating, setEstimating] = useState(false)

  /**
   * Start a retrieval run directly; price an end-to-end run first.
   *
   * A retrieval run calls no model and cannot cost anything, so a
   * confirmation there would be noise. An end-to-end run spends tokens per
   * item, and the number is shown before it can be started.
   */
  const handleRun = async () => {
    if (mode !== 'end_to_end') {
      await onStart('retrieval')
      return
    }
    setEstimating(true)
    // No model name is sent: the page does not know which model rag will
    // use, so the estimate comes back flagged as unpriced rather than priced
    // against a guess. `estimateDescription` says so in words.
    const priced = await onEstimate(dataset?.item_count || 0, mode, null)
    setEstimating(false)
    if (priced) setEstimate(priced)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={mode} onValueChange={setMode} className="w-[190px]" aria-label={t('evalSingle.runMode')}>
          {Object.entries(EVAL_MODE_LABEL_KEYS).map(([value, labelKey]) => (
            <SelectItem key={value} value={value}>
              {t(labelKey)}
            </SelectItem>
          ))}
        </Select>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRun}
          disabled={busy || running || estimating || !datasetId}
          leftIcon={<Play size={13} />}
        >
          {t(running
            ? 'evalSingle.running'
            : estimating
              ? 'evalSingle.estimating'
              : 'evalSingle.run')}
        </Button>
      </div>

      <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
        {t(EVAL_MODE_HELP_KEYS[mode])}
      </p>

      {running && (
        <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
          {t('evalSingle.progress', {
            scored: formatCount(run?.per_item?.length || 0),
            total: formatCount(dataset?.item_count),
          })}{' '}
          {t(run?.mode === 'end_to_end'
            ? 'evalSingle.endToEndNote'
            : 'evalSingle.retrievalNote')}
        </p>
      )}

      <ConfirmModal
        open={Boolean(estimate)}
        onOpenChange={(next) => {
          if (!next) setEstimate(null)
        }}
        title={t('evalSingle.confirmTitle')}
        description={estimateDescription(estimate, t)}
        confirmLabel={t('evalSingle.confirmRun')}
        onConfirm={async () => {
          setEstimate(null)
          await onStart('end_to_end')
        }}
      />
    </div>
  )
}

/**
 * The sentence shown before an end-to-end run starts.
 *
 * States the estimate as an estimate, and says plainly when a $0.00 figure
 * means "this model has no configured price" rather than "this is free".
 */
export function estimateDescription(estimate, t) {
  if (!estimate) return ''
  const translateWith = t || ((key, vars) => translate(DEFAULT_LOCALE, key, vars))
  const tokens = (estimate.estimated_tokens_in || 0) + (estimate.estimated_tokens_out || 0)
  const base = translateWith('evalSingle.estimate', {
    items: formatCount(estimate.item_count),
    calls: estimate.calls_per_item,
    tokens: formatCount(tokens),
    cost: formatCost(estimate.estimated_cost_usd),
  })
  return estimate.model_priced
    ? base
    : `${base} ${translateWith(UNPRICED_MODEL_NOTE_KEY)}`
}
