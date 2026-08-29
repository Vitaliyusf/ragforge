'use client'

import { ChevronRight, HelpCircle } from 'lucide-react'
import { resolveTone } from '@/components/status/statusTone'
import { phaseStatusMeta } from '../../evalProfiles'

/**
 * The run as a causal chain: validation, then each phase, in the order the
 * server executes them.
 *
 * The point of the flow is the distinction a status column cannot make. A
 * stage that never ran because an earlier one failed says which stage
 * stopped it, in words, and keeps the neutral tone: skipped is not failed,
 * and a reader who cannot tell them apart debugs the wrong stage. A stage
 * this deployment cannot execute reads "Not supported" for the same reason.
 */
export default function ExecutionFlow({ stages = [] }) {
  if (!stages.length) return null

  return (
    <div>
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-2" aria-label="Execution flow">
        {stages.map((stage, index) => {
          const meta = stage.status === 'unknown' ? UNKNOWN_META : phaseStatusMeta(stage.status)
          const Icon = meta.icon
          const tone = resolveTone(meta.variant)
          return (
            <li key={stage.key} className="flex items-center gap-1">
              <span
                className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[13px]"
                style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
              >
                <Icon
                  size={13}
                  aria-hidden="true"
                  className={meta.spin ? 'animate-spin' : undefined}
                  style={{ color: tone.fg }}
                />
                <span style={{ color: 'var(--fg)' }}>{stage.label}</span>
                <span style={{ color: 'var(--fg-soft)' }}>{meta.label}</span>
              </span>
              {index < stages.length - 1 && (
                <ChevronRight size={13} aria-hidden="true" style={{ color: 'var(--fg-soft)' }} />
              )}
            </li>
          )
        })}
      </ol>

      {/* The reasons, in full, under the chain rather than inside a tooltip
          nobody hovers. This is where "skipped" stops being ambiguous. */}
      <dl className="mt-3 grid gap-1 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {stages
          .filter((stage) => stage.note)
          .map((stage) => (
            <div key={stage.key} className="flex flex-wrap gap-x-2">
              <dt className="font-medium" style={{ color: 'var(--fg-muted)' }}>
                {stage.label}:
              </dt>
              <dd>{stage.note}</dd>
            </div>
          ))}
      </dl>
    </div>
  )
}

/** A stage nobody measured. Muted, and never dressed as a pass or a failure. */
const UNKNOWN_META = { label: 'Not verified', variant: 'default', icon: HelpCircle }
