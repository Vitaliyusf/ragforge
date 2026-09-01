'use client'

import { motion } from 'framer-motion'
import { ArrowUpRight, Sparkles } from 'lucide-react'
import { useI18n } from '@/i18n'

/** Empty-thread state: what this workspace is, and a few ways in. */
export default function ChatWelcome({ suggestedPrompts, onSuggestedPrompt }) {
  const { isRTL, t } = useI18n()

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto flex min-h-[380px] max-w-3xl flex-col items-center justify-center py-10 text-center"
    >
      <div
        className="mb-6 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium text-primary"
        style={{ background: 'var(--primary-soft)', borderColor: 'rgba(var(--primary-rgb) / 0.18)' }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-primary" />
        {t('chat.welcomeBadge')}
      </div>

      <div className="relative mb-5">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-soft">
          <Sparkles className="text-primary" size={27} />
        </div>
        <div className="absolute -end-2 -top-2 h-5 w-5 rounded-full border-4 border-[var(--surface)] bg-accent" />
      </div>

      <h2 className="text-2xl font-semibold tracking-tight text-text-primary md:text-3xl">
        {t('chat.welcomeTitle')}
      </h2>
      <p className="mb-7 mt-2 max-w-lg text-[15px] leading-relaxed text-text-muted">
        {t('chat.welcomeSubtitle')}
      </p>

      <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {suggestedPrompts.map((prompt, index) => (
          <motion.button
            key={prompt}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 * index }}
            onClick={() => onSuggestedPrompt(prompt)}
            dir="auto"
            className="group flex min-h-14 items-center justify-between gap-3 rounded-2xl border border-border bg-bg-elevated px-4 py-3 text-start text-[15px] font-medium text-text-secondary shadow-sm transition-all duration-200 hover:border-border-hover hover:text-text-primary hover:shadow-md focus-visible:outline-hidden focus-visible:ring-2"
          >
            <span>{prompt}</span>
            {/* A directional arrow: it leans the way the reader is going, so
                in Hebrew it points up-left and nudges left on hover. */}
            <ArrowUpRight
              size={15}
              className={`shrink-0 text-text-muted transition-transform group-hover:text-primary ${
                isRTL ? '-scale-x-100 group-hover:-translate-x-0.5' : 'group-hover:translate-x-0.5'
              }`}
            />
          </motion.button>
        ))}
      </div>
    </motion.div>
  )
}
