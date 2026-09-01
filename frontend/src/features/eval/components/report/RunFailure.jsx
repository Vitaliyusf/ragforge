'use client'

import { AlertTriangle, Download, RotateCcw } from 'lucide-react'
import Button from '@/components/ui/Button'
import { Callout, Disclosure } from './primitives'
import { useI18n } from '@/i18n'

/**
 * What went wrong, in the order somebody acting on it needs to read it.
 *
 * What happened → impact → likely cause → what to do → the raw text. The
 * exception string is the last thing on this list, not the first: a stack
 * trace as a headline tells a reader that something broke and nothing about
 * whether their numbers are usable.
 *
 * A cause appears only when the error text supports one, and an action
 * button appears only when this page can actually perform it. An offer that
 * does nothing costs a click and a rebuilt expectation to teach the same
 * thing as no offer at all.
 */
export default function RunFailure({ failure, onRetry, onDownload, busy }) {
  const { t } = useI18n()
  if (!failure) return null
  const tone = failure.status === 'partial' ? 'warning' : 'danger'

  return (
    <Callout tone={tone} icon={AlertTriangle} title={failure.title}>
      <dl className="grid gap-2">
        <div>
          <dt className="label-xs">{t('evalReport.whatHappened')}</dt>
          <dd>{failure.happened}</dd>
        </div>
        <div>
          <dt className="label-xs">{t('evalReport.impact')}</dt>
          <dd>{failure.impact}</dd>
        </div>
        {failure.cause && (
          <div>
            <dt className="label-xs">{t('evalReport.likelyCause')}</dt>
            <dd>{failure.cause}</dd>
          </div>
        )}
      </dl>

      {failure.actions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {failure.actions.includes('retry') && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={onRetry}
              leftIcon={<RotateCcw size={13} />}
            >
              {t('evalReport.retryRun')}
            </Button>
          )}
          {failure.actions.includes('download') && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => onDownload()}
              leftIcon={<Download size={13} />}
            >
              {t('evalReport.download')}
            </Button>
          )}
        </div>
      )}

      {failure.technical && (
        <div className="mt-2">
          <Disclosure
            title={t('evalReport.technicalDetails')}
            summary={t('evalReport.technicalSummary')}
          >
            {/* The service's own error text: never translated, never reordered. */}
            <p dir="ltr" className="font-mono text-[12px] break-words text-left [unicode-bidi:isolate]">
              {failure.technical}
            </p>
          </Disclosure>
        </div>
      )}
    </Callout>
  )
}
