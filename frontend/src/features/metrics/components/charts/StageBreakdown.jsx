'use client'

import { useMemo } from 'react'

const VIEW_W = 100
const VIEW_H = 10
const DEFAULT_COLORS = [
  'var(--primary)',
  'var(--info)',
  'var(--success)',
  'var(--warning)',
  'var(--danger)',
]

/**
 * Horizontal stacked bar showing where a turn's time goes.
 *
 * @param {Array<{label: string, value: number, color?: string}>} stages
 */
export default function StageBreakdown({
  stages = [],
  height = 18,
  valueFormat = (value) => String(value),
  label = 'Stage breakdown',
}) {
  const model = useMemo(() => {
    const cleaned = (stages || [])
      .filter((stage) => stage && Number.isFinite(Number(stage.value)) && Number(stage.value) > 0)
      .map((stage, index) => ({
        label: String(stage.label ?? ''),
        value: Number(stage.value),
        color: stage.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
      }))

    const total = cleaned.reduce((sum, stage) => sum + stage.value, 0)
    // No positive stage means no bar to divide up — a zero total would make
    // every segment width NaN.
    if (!cleaned.length || total <= 0) return null

    let offset = 0
    return {
      total,
      segments: cleaned.map((stage) => {
        const width = (stage.value / total) * VIEW_W
        const segment = { ...stage, x: offset, width, share: (stage.value / total) * 100 }
        offset += width
        return segment
      }),
    }
  }, [stages])

  if (!model) return null

  const summary = `${label}. ${model.segments
    .map((segment) => `${segment.label} ${valueFormat(segment.value)}`)
    .join(', ')}.`

  return (
    <div className="w-full">
      <svg
        className="w-full overflow-hidden rounded-full"
        style={{ height }}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={summary}
      >
        {model.segments.map((segment) => (
          <rect
            key={segment.label}
            x={segment.x}
            y="0"
            width={segment.width}
            height={VIEW_H}
            fill={segment.color}
          >
            <title>
              {`${segment.label}: ${valueFormat(segment.value)} (${Math.round(segment.share)}%)`}
            </title>
          </rect>
        ))}
      </svg>

      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5">
        {model.segments.map((segment) => (
          <span key={segment.label} className="flex items-center gap-1.5 text-[12px]">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: segment.color }}
            />
            <span style={{ color: 'var(--fg-muted)' }}>{segment.label}</span>
            <span className="font-medium tabular-nums" style={{ color: 'var(--fg)' }}>
              {valueFormat(segment.value)}
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
