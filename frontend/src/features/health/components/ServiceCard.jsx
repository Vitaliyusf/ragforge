'use client'

import { memo } from 'react'
import { motion } from 'framer-motion'
import { Server } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { STATUS_CONFIG, SERVICE_LABELS } from './healthConfig'

function ServiceCard({ name, info, index = 0 }) {
  const cfg = STATUS_CONFIG[info.status] || STATUS_CONFIG.unknown
  const Icon = cfg.icon

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="relative overflow-hidden rounded-2xl border p-4 transition-all duration-200 hover:shadow-md"
      style={{
        background: 'var(--surface-elevated)',
        borderColor: cfg.border,
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div className="absolute inset-y-0 left-0 w-0.5" style={{ background: cfg.iconColor }} />
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl" style={{ background: cfg.bg, color: cfg.iconColor }}>
          <Server size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[13px] font-semibold text-text-primary">{SERVICE_LABELS[name] || name}</span>
            <Badge variant={cfg.badgeVariant} size="xs" dot>{cfg.label}</Badge>
          </div>
          <p className="mt-1 truncate text-xs text-text-muted">
            {info.message || (info.status === 'healthy' ? 'Responding normally' : 'Service requires attention')}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border/70 pt-2.5">
        <span className="flex items-center gap-1.5 text-xs text-text-muted">
          <Icon size={11} style={{ color: cfg.iconColor }} /> Health check
        </span>
        {info.port && (
          <span className="rounded-md bg-bg-tertiary px-1.5 py-0.5 font-mono text-xs text-text-muted">:{info.port}</span>
        )}
      </div>
    </motion.div>
  )
}

export default memo(ServiceCard)
