'use client'

import { useMemo, useState } from 'react'

const VIEW_W = 600
const GRIDLINES = 4
const DEFAULT_COLORS = ['var(--primary)', 'var(--info)', 'var(--success)', 'var(--warning)']

/** Keep only well-formed, finite [timestamp, value] pairs. */
function finitePoints(points) {
  return (points || [])
    .filter((p) => Array.isArray(p) && Number.isFinite(Number(p[0])) && Number.isFinite(Number(p[1])))
    .map((p) => [Number(p[0]), Number(p[1])])
}

/**
 * One or more line series over time.
 *
 * @param {Array<{name: string, points: Array<[number, number]>, color?: string}>} series
 */
export default function TimeSeries({
  series = [],
  height = 180,
  yFormat = (value) => String(value),
  label = 'Time series',
}) {
  const [hover, setHover] = useState(null)

  const model = useMemo(() => {
    const cleaned = (series || [])
      .map((entry, index) => ({
        name: entry?.name || `Series ${index + 1}`,
        color: entry?.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
        points: finitePoints(entry?.points),
      }))
      .filter((entry) => entry.points.length > 0)

    const all = cleaned.flatMap((entry) => entry.points)
    // Matches MiniSparkline's `data.length < 2` guard: one point is not a line.
    if (all.length < 2) return null

    const times = all.map((p) => p[0])
    const values = all.map((p) => p[1])
    const tMin = Math.min(...times)
    const tMax = Math.max(...times)
    const lo = Math.min(...values)
    const hi = Math.max(...values)

    // A flat series has a zero value range. Dividing by it produces NaN
    // coordinates, which silently break the entire SVG, so pad it into a
    // real range and draw the line down the middle.
    const flat = hi === lo
    const vMin = flat ? lo - 1 : lo
    const vMax = flat ? hi + 1 : hi
    const tRange = tMax - tMin
    const vRange = vMax - vMin

    const xFor = (t) => (tRange === 0 ? VIEW_W / 2 : ((t - tMin) / tRange) * VIEW_W)
    const yFor = (v) => height - ((v - vMin) / vRange) * height

    return {
      tMin,
      tRange,
      lines: cleaned.map((entry) => ({
        ...entry,
        d: entry.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xFor(p[0])},${yFor(p[1])}`).join(' '),
      })),
      ticks: Array.from({ length: GRIDLINES }, (_, i) => {
        const value = vMin + (vRange * i) / (GRIDLINES - 1)
        return { value, y: yFor(value) }
      }),
    }
  }, [series, height])

  if (!model) return null

  const handleMove = (event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    if (!rect.width) return
    const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
    const target = model.tMin + fraction * model.tRange
    setHover({
      fraction,
      entries: model.lines.map((line) => {
        const nearest = line.points.reduce((best, p) =>
          Math.abs(p[0] - target) < Math.abs(best[0] - target) ? p : best
        )
        return { name: line.name, color: line.color, value: nearest[1] }
      }),
    })
  }

  const summary = `${label}. ${model.lines.map((l) => l.name).join(', ')}.`

  return (
    <div className="w-full">
      <div className="relative flex w-full gap-2">
        {/* Tick labels live outside the SVG: the stretched viewBox would
            squash any <text> placed inside it. */}
        <div
          className="relative shrink-0 text-right text-[11px] tabular-nums"
          style={{ height, width: '3.5rem', color: 'var(--fg-muted)' }}
        >
          {model.ticks.map((tick) => (
            <span
              key={tick.value}
              className="absolute right-0 -translate-y-1/2"
              style={{ top: tick.y }}
            >
              {yFormat(tick.value)}
            </span>
          ))}
        </div>

        <div
          className="relative min-w-0 flex-1"
          style={{ height }}
          onMouseMove={handleMove}
          onMouseLeave={() => setHover(null)}
        >
          <svg
            className="h-full w-full"
            viewBox={`0 0 ${VIEW_W} ${height}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={summary}
          >
            {model.ticks.map((tick) => (
              <line
                key={tick.value}
                x1="0"
                x2={VIEW_W}
                y1={tick.y}
                y2={tick.y}
                stroke="var(--border)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {model.lines.map((line) => (
              <path
                key={line.name}
                d={line.d}
                fill="none"
                stroke={line.color}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {hover && (
              <line
                x1={hover.fraction * VIEW_W}
                x2={hover.fraction * VIEW_W}
                y1="0"
                y2={height}
                stroke="var(--fg-soft)"
                strokeWidth="1"
                strokeDasharray="3 3"
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>

          {hover && (
            <div
              className="pointer-events-none absolute top-1 z-10 -translate-x-1/2 rounded-lg px-2.5 py-1.5 text-[12px]"
              style={{
                left: `${hover.fraction * 100}%`,
                background: 'var(--surface-elevated)',
                border: '1px solid var(--border)',
                boxShadow: 'var(--shadow-md)',
                color: 'var(--fg)',
              }}
            >
              {hover.entries.map((entry) => (
                <div key={entry.name} className="flex items-center gap-1.5 whitespace-nowrap">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: entry.color }}
                  />
                  <span style={{ color: 'var(--fg-muted)' }}>{entry.name}</span>
                  <span className="font-medium tabular-nums">{yFormat(entry.value)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {model.lines.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 pl-[4rem]">
          {model.lines.map((line) => (
            <span
              key={line.name}
              className="flex items-center gap-1.5 text-[12px]"
              style={{ color: 'var(--fg-muted)' }}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: line.color }} />
              {line.name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
