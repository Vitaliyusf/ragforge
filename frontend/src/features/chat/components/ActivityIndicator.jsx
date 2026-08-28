'use client'

import { motion } from 'framer-motion'
import ProgressBar from '@/components/ui/ProgressBar'
import { describeStage } from '@/features/chat/utils/activityStages'

/**
 * The live execution state for the turn currently being answered.
 *
 * Every label here is a translation of a `status` event the RAG graph actually
 * emitted, and the bar is drawn only for a progress number the backend
 * reported — there is no simulated advance.
 */
export default function ActivityIndicator({ status }) {
  const stage = describeStage(status)
  if (!stage) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="mx-auto mt-3 flex max-w-[46rem] items-center gap-2.5 px-1"
      role="status"
      aria-live="polite"
    >
      <span className="flex gap-1" aria-hidden="true">
        {[0, 0.15, 0.3].map((delay) => (
          <span
            key={delay}
            className="h-1.5 w-1.5 rounded-full bg-[var(--primary)] motion-safe:animate-pulse"
            style={{ animationDelay: `${delay}s` }}
          />
        ))}
      </span>
      <span className="text-[13px] text-[var(--fg-muted)]">{stage.label}</span>
      {stage.progress != null ? (
        <ProgressBar value={stage.progress} className="w-24" aria-label={stage.label} />
      ) : null}
    </motion.div>
  )
}
