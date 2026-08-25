'use client'

import { useMemo } from 'react'

const VIEW_W = 600
const VIEW_H = 100
const GAP = 0.18 // share of each slot left as spacing between bars

/**
 * Bucketed distribution as a bar chart.
 *
 * @param {Array<{label: string, count: number}>} buckets
 */
export default function Histogram({
  buckets = [],
  height = 140,
  accent = 'var(--primary)',
  label = 'Distribution',
  valueFormat = (value) => String(value),
  // Percentage-of-total is meaningful for a count distribution but not for
  // a bar chart of latencies, where the bars do not sum to anything.
  showShare = true,
}) {
  const model = useMemo(() => {
    const cleaned = (buckets || [])
      .filter((bucket) => bucket && Number.isFinite(Number(bucket.count)))
      .map((bucket) => ({ label: String(bucket.label ?? ''), count: Number(bucket.count) }))

    const total = cleaned.reduce((sum, bucket) => sum + bucket.count, 0)
    // Every bucket empty means there is nothing to scale against; dividing
    // by that zero max would put NaN in every rect.
    if (!cleaned.length || total <= 0) return null

    const max = Math.max(...cleaned.map((bucket) => bucket.count))
    const slot = VIEW_W / cleaned.length
    const barWidth = slot * (1 - GAP)

    return {
      total,
      bars: cleaned.map((bucket, index) => {
        const barHeight = (bucket.count / max) * VIEW_H
        return {
          ...bucket,
          x: index * slot + (slot - barWidth) / 2,
          y: VIEW_H - barHeight,
          width: barWidth,
          height: barHeight,
          share: Math.round((bucket.count / total) * 100),
        }
      }),
    }
  }, [buckets])

  if (!model) return null

  const summary = `${label}. ${model.bars
    .map((bar) => `${bar.label}: ${valueFormat(bar.count)}`)
    .join(', ')}.`

  return (
    <div className="w-full">
      <svg
        className="w-full"
        style={{ height }}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={summary}
      >
        {model.bars.map((bar) => (
          <rect
            key={bar.label}
            x={bar.x}
            y={bar.y}
            width={bar.width}
            height={bar.height}
            fill={accent}
            opacity="0.85"
          >
            <title>
              {showShare
                ? `${bar.label}: ${valueFormat(bar.count)} (${bar.share}%)`
                : `${bar.label}: ${valueFormat(bar.count)}`}
            </title>
          </rect>
        ))}
      </svg>

      {/* Labels sit below the stretched viewBox rather than inside it. */}
      <div className="mt-1.5 flex w-full">
        {model.bars.map((bar) => (
          <span
            key={bar.label}
            className="min-w-0 flex-1 truncate text-center text-[11px] tabular-nums"
            style={{ color: 'var(--fg-muted)' }}
            title={`${bar.label}: ${valueFormat(bar.count)}`}
          >
            {bar.label}
          </span>
        ))}
      </div>
    </div>
  )
}
