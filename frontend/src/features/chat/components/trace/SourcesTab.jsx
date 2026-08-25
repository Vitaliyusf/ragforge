'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { DataCell } from '@/components/ui/DataDisplay'
import ProgressBar from '@/components/ui/ProgressBar'
import { scoreColor, Empty } from './shared'

function SourcesTab({ sources, retrievalSummary }) {
  const [expandedIndex, setExpandedIndex] = useState(null)

  if (!sources.length) {
    return <Empty label="No sources retrieved for this turn" />
  }

  const topScore   = sources[0]?.score ?? 0
  const bottomScore = sources[sources.length - 1]?.score ?? 0

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <DataCell reverse center mono label="Chunks" value={sources.length} />
        <DataCell reverse center mono label="Top score" value={topScore ? `${(topScore * 100).toFixed(0)}%` : '—'} />
        <DataCell reverse center mono label="Min score" value={bottomScore ? `${(bottomScore * 100).toFixed(0)}%` : '—'} />
      </div>

      <div className="space-y-2">
        {sources.map((src, index) => {
          const score  = src.score ?? src.similarity ?? null
          const pct    = score != null ? score * 100 : null
          const color  = score != null ? scoreColor(score) : 'var(--fg-soft)'
          const name   = src.source_name || src.source || src.filename || `chunk-${index + 1}`
          const isOpen = expandedIndex === index

          return (
            <div key={src.chunk_id || index} className="rounded-lg border border-border bg-bg-tertiary overflow-hidden">
              <button
                type="button"
                onClick={() => setExpandedIndex(isOpen ? null : index)}
                className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-bg-elevated transition-colors"
              >
                <div
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-xs font-bold text-white"
                  style={{ backgroundColor: color }}
                >
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-text-primary">{name}</div>
                  <ProgressBar
                    value={pct}
                    color={color}
                    thickness="xs"
                    track="bg-bg-elevated"
                    className="mt-1"
                  />
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-text-muted">
                    {pct != null ? (
                      <span style={{ color }} className="font-mono font-semibold">{pct.toFixed(1)}%</span>
                    ) : null}
                    {src.chunk_index != null ? <span>chunk #{src.chunk_index}</span> : null}
                    {src.page != null ? <span>p.{src.page}</span> : null}
                  </div>
                </div>
                {isOpen ? <ChevronUp size={12} className="mt-1 shrink-0 text-text-muted" /> : <ChevronDown size={12} className="mt-1 shrink-0 text-text-muted" />}
              </button>

              <AnimatePresence initial={false}>
                {isOpen ? (
                  <motion.div
                    key="preview"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="border-t border-border px-3 pb-3 pt-2">
                      <p className="text-xs leading-relaxed text-text-muted line-clamp-6">
                        {src.text_preview || src.text || 'No preview available'}
                      </p>
                    </div>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default SourcesTab
