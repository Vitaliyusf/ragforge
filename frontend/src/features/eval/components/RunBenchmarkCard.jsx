'use client'

import { useState } from 'react'
import { AlertTriangle, ChevronRight, Play } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import { ConfirmModal } from '@/components/ui/Modal'
import Select, { SelectItem } from '@/components/ui/Select'
import { formatCount } from '@/features/metrics/components/metricsConfig'
import {
  COST_VARIANTS,
  DEFAULT_PROFILE_ID,
  EXPENSIVE_PROFILE_NOTE_KEY,
  PROFILES,
  PROFILES_BY_ID,
  PROFILE_HELP_KEY,
  SINGLE_EVAL_HELP_KEY,
  isExpensive,
  profilePhaseNames,
  profilePhaseSummary,
  statusMeta,
} from '../evalProfiles'
import { useI18n } from '@/i18n'

/**
 * The page's one primary action.
 *
 * The benchmark profile is the workflow; the single evaluation below it is
 * the escape hatch. Only one violet button appears on this surface, so
 * there is never a question of which run the page wants you to start.
 */
export default function RunBenchmarkCard({
  itemCount,
  ready,
  busy,
  benchmark,
  running,
  onStart,
  children,
}) {
  const { t } = useI18n()
  const [profileId, setProfileId] = useState(DEFAULT_PROFILE_ID)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const profile = PROFILES_BY_ID[profileId]
  const items = Number.isFinite(itemCount)
    ? t('evalRun.itemCount', { count: formatCount(itemCount) })
    : null
  const status = benchmark?.status ? statusMeta(benchmark.status, t) : null

  return (
    <Card>
      <CardHeader title={t('evalRun.title')} description={t(PROFILE_HELP_KEY)} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1">
          <span className="label-xs">{t('evalRun.profile')}</span>
          <Select
            value={profileId}
            onValueChange={setProfileId}
            disabled={busy || running}
            aria-label={t('evalRun.benchmarkProfile')}
            className="mt-1 w-full sm:max-w-[380px]"
            valueLabel={
              <span className="flex min-w-0 items-center gap-2">
                <span className="truncate">{t(profile.labelKey)}</span>
                <Badge size="xs" variant={COST_VARIANTS[profile.cost]}>
                  {t(profile.costKey)}
                </Badge>
              </span>
            }
          >
            {PROFILES.map((entry) => (
              <SelectItem
                key={entry.id}
                value={entry.id}
                textValue={t(entry.labelKey)}
                className="items-start gap-6 py-2"
              >
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex items-center gap-2 text-[15px] font-medium">
                    {t(entry.labelKey)}
                    <Badge size="xs" variant={COST_VARIANTS[entry.cost]}>
                      {t(entry.costKey)}
                    </Badge>
                  </span>
                  <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                    {profilePhaseSummary(entry, t)}
                    {items ? ` · ${items}` : ''}
                  </span>
                </span>
              </SelectItem>
            ))}
          </Select>
        </div>

        <Button
          onClick={() => setConfirmOpen(true)}
          disabled={!ready || busy || running}
          leftIcon={<Play size={14} />}
          className="w-full sm:w-auto"
        >
          {t(running ? 'evalRun.running' : 'evalRun.start')}
        </Button>
      </div>

      <p className="mt-3 text-[13px]" style={{ color: 'var(--fg-muted)' }}>
        {ready
          ? t('evalRun.readySummary', {
              phases: profilePhaseSummary(profile, t),
              target: items || t('evalRun.selectedGoldenSet'),
            })
          : t('evalRun.notReady')}
      </p>

      {isExpensive(profile) && (
        <p
          className="mt-2 flex items-center gap-2 text-[13px]"
          style={{ color: 'var(--warning)' }}
        >
          <AlertTriangle size={13} aria-hidden="true" />
          {t(EXPENSIVE_PROFILE_NOTE_KEY)}
        </p>
      )}

      {status && (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-[13px]">
          <Badge variant={status.variant} icon={status.icon} spin={status.spin}>
            {status.label}
          </Badge>
          <span style={{ color: 'var(--fg-muted)' }}>
            {running ? 'Current run' : 'Latest run'}
            {benchmark?.profile
              ? ` · ${PROFILES_BY_ID[benchmark.profile]?.labelKey
                  ? t(PROFILES_BY_ID[benchmark.profile].labelKey)
                  : benchmark.profile}`
              : ''}
          </span>
        </p>
      )}

      {children && (
        <details
          className="group mt-5 rounded-xl border"
          style={{ borderColor: 'var(--border)' }}
        >
          <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-3 py-2.5 text-[13px] font-medium focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
            <ChevronRight
              size={14}
              aria-hidden="true"
              className="shrink-0 transition-transform duration-150 group-open:rotate-90"
            />
            Single evaluation
            <span className="font-normal" style={{ color: 'var(--fg-soft)' }}>
              {t(SINGLE_EVAL_HELP_KEY)}
            </span>
          </summary>
          <div className="border-t px-3 py-3" style={{ borderColor: 'var(--border)' }}>
            {children}
          </div>
        </details>
      )}

      <ConfirmModal
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t('evalRun.confirmTitle', { profile: t(profile.labelKey) })}
        description={
          t('evalRun.confirmDescription', {
            phases: profilePhaseNames(profile, t),
            target: items || t('evalRun.selectedDataset'),
          }) + (isExpensive(profile) ? ` ${t('evalRun.expensiveSuffix')}` : '')
        }
        confirmLabel={t('evalRun.start')}
        variant={isExpensive(profile) ? 'danger' : 'primary'}
        onConfirm={() => {
          setConfirmOpen(false)
          onStart(profile.id)
        }}
      />
    </Card>
  )
}
