'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { DataCell } from '@/components/ui/DataDisplay'
import ProgressBar from '@/components/ui/ProgressBar'
import { formatScore, scoreColor } from '@/features/chat/utils/answerQuality'
import { Empty } from './shared'
import { useI18n } from '@/i18n'

/** Retrieved passages with their retrieval/reranker scores. */
export default function RetrievalSection({ sources, retrievalSummary }) {
  const { t } = useI18n()
  const [expandedIndex, setExpandedIndex] = useState(null)

  if (!sources?.length) {
    return <Empty label={t('inspector.emptyRetrieval')} />
  }

  const scores = sources
    .map((source) => source.score ?? source.similarity ?? null)
    .filter(Number.isFinite)
  const chunkCount = Number.isFinite(retrievalSummary?.chunk_count)
    ? retrievalSummary.chunk_count
    : sources.length

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <DataCell reverse center mono label={t('inspector.chunks')} value={chunkCount} />
        <DataCell reverse center mono label={t('inspector.topScore')} value={scores.length ? formatScore(Math.max(...scores)) : '—'} />
        <DataCell reverse center mono label={t('inspector.minScore')} value={scores.length ? formatScore(Math.min(...scores)) : '—'} />
      </div>

      <div className="space-y-2">
        {sources.map((source, index) => {
          const score = source.score ?? source.similarity ?? null
          const percent = Number.isFinite(score) ? score * 100 : null
          const color = scoreColor(score)
          const name = source.source_name || source.source || source.filename || source.title || `chunk-${index + 1}`
          const isOpen = expandedIndex === index

          return (
            <div key={source.chunk_id || index} className="overflow-hidden rounded-lg border border-border bg-bg-tertiary">
              <button
                type="button"
                onClick={() => setExpandedIndex(isOpen ? null : index)}
                className="flex w-full items-start gap-2.5 px-3 py-2.5 text-start transition-colors hover:bg-bg-elevated"
              >
                <div
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-xs font-bold text-white"
                  style={{ backgroundColor: color }}
                >
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div dir="auto" className="truncate text-[13px] font-medium text-text-primary">{name}</div>
                  <ProgressBar value={percent} color={color} thickness="xs" track="bg-bg-elevated" className="mt-1" />
                  <div dir="ltr" className="mt-0.5 flex items-center gap-2 text-xs text-text-muted">
                    {percent != null ? (
                      <span style={{ color }} className="font-mono font-semibold">{percent.toFixed(1)}%</span>
                    ) : null}
                    {source.chunk_index != null
                      ? <span>{t('inspector.chunkIndex', { index: source.chunk_index })}</span>
                      : null}
                    {source.page != null
                      ? <span>{t('inspector.pageShort', { page: source.page })}</span>
                      : null}
                  </div>
                </div>
                {isOpen
                  ? <ChevronUp size={12} className="mt-1 shrink-0 text-text-muted" />
                  : <ChevronDown size={12} className="mt-1 shrink-0 text-text-muted" />}
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
                      <p dir="auto" className="line-clamp-6 text-xs leading-relaxed text-text-muted">
                        {source.text_preview || source.text || t('inspector.noPreview')}
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
