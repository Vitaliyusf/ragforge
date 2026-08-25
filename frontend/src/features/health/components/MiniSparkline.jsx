'use client'

function MiniSparkline({ data, height = 28 }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data, 1)
  const w   = 100
  const points = data.map((v, i) => `${(i / (data.length - 1)) * w},${height - (v / max) * height}`).join(' ')
  return (
    <svg width={w} height={height} className="opacity-60">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--success)' }} />
    </svg>
  )
}

export default MiniSparkline
