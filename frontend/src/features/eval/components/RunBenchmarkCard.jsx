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
  EXPENSIVE_PROFILE_NOTE,
  PROFILES,
  PROFILES_BY_ID,
  PROFILE_HELP,
  SINGLE_EVAL_HELP,
  isExpensive,
  profilePhaseNames,
  profilePhaseSummary,
  statusMeta,
} from '../evalProfiles'

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
  const [profileId, setProfileId] = useState(DEFAULT_PROFILE_ID)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const profile = PROFILES_BY_ID[profileId]
  const items = Number.isFinite(itemCount) ? `${formatCount(itemCount)} items` : null
  const status = benchmark?.status ? statusMeta(benchmark.status) : null

  return (
    <Card>
      <CardHeader title="Run benchmark" description={PROFILE_HELP} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1">
          <span className="label-xs">Profile</span>
          <Select
            value={profileId}
            onValueChange={setProfileId}
            disabled={busy || running}
            aria-label="Benchmark profile"
            className="mt-1 w-full sm:max-w-[380px]"
            valueLabel={
              <span className="flex min-w-0 items-center gap-2">
                <span className="truncate">{profile.label}</span>
                <Badge size="xs" variant={COST_VARIANTS[profile.cost]}>
                  {profile.cost}
                </Badge>
              </span>
            }
          >
            {PROFILES.map((entry) => (
              <SelectItem
                key={entry.id}
                value={entry.id}
                textValue={entry.label}
                className="items-start gap-6 py-2"
              >
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex items-center gap-2 text-[15px] font-medium">
                    {entry.label}
                    <Badge size="xs" variant={COST_VARIANTS[entry.cost]}>
                      {entry.cost}
                    </Badge>
                  </span>
                  <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                    {profilePhaseSummary(entry)}
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
          {running ? 'Benchmark running…' : 'Start benchmark'}
        </Button>
      </div>

      <p className="mt-3 text-[13px]" style={{ color: 'var(--fg-muted)' }}>
        {ready
          ? `${profilePhaseSummary(profile)} over ${items || 'the selected golden set'}.`
          : 'Import and validate a golden set before starting a benchmark run.'}
      </p>

      {isExpensive(profile) && (
        <p
          className="mt-2 flex items-center gap-2 text-[13px]"
          style={{ color: 'var(--warning)' }}
        >
          <AlertTriangle size={13} aria-hidden="true" />
          {EXPENSIVE_PROFILE_NOTE}
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
              ? ` · ${PROFILES_BY_ID[benchmark.profile]?.label || benchmark.profile}`
              : ''}
          </span>
        </p>
      )}

      {children && (
        <details
          className="group mt-5 rounded-xl border"
          style={{ borderColor: 'var(--border)' }}
        >
          <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-3 py-2.5 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
            <ChevronRight
              size={14}
              aria-hidden="true"
              className="shrink-0 transition-transform duration-150 group-open:rotate-90"
            />
            Single evaluation
            <span className="font-normal" style={{ color: 'var(--fg-soft)' }}>
              {SINGLE_EVAL_HELP}
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
        title={`Run ${profile.label}?`}
        description={
          `${profilePhaseNames(profile)} over ${items || 'the selected dataset'}.` +
          (isExpensive(profile) ? ' This is an expensive profile.' : '')
        }
        confirmLabel="Start benchmark"
        variant={isExpensive(profile) ? 'danger' : 'primary'}
        onConfirm={() => {
          setConfirmOpen(false)
          onStart(profile.id)
        }}
      />
    </Card>
  )
}
