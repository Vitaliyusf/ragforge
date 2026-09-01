'use client'

import { memo } from 'react'
import { motion } from 'framer-motion'
import { Server } from 'lucide-react'
import DomainStatus from '@/components/status/DomainStatus'
import { STATUS_DOMAINS } from '@/components/status/statusDomains'
import DeepLink from '@/components/observability/DeepLink'
import { logsLinkForService } from '@/lib/observability/deepLinks'
import { STATUS_CONFIG, SERVICE_LABELS } from './healthConfig'
import { useI18n } from '@/i18n'

function ServiceCard({ name, info, index = 0 }) {
  const { t } = useI18n()
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
      <div className="absolute inset-y-0 start-0 w-0.5" style={{ background: cfg.iconColor }} />
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl" style={{ background: cfg.bg, color: cfg.iconColor }}>
          <Server size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            {/* Backend service names are canonical and stay English in both
                locales — there is no Hebrew name for "RAG Orchestrator". */}
            <span dir="ltr" className="truncate text-[13px] font-semibold text-text-primary [unicode-bidi:isolate]">
              {SERVICE_LABELS[name] || name}
            </span>
            <DomainStatus domain={STATUS_DOMAINS.SERVICE} state={info.status} />
          </div>
          <p className="mt-1 truncate text-xs text-text-muted">
            {info.message
              || t(info.status === 'healthy'
                ? 'health.serviceHealthyMessage'
                : 'health.serviceAttentionMessage')}
          </p>
          {/* Probe results, named for what they are. "Live" used to appear
              here, on the log stream and on the composer meaning three
              different things; a liveness probe is not a live connection. */}
          <div className="mt-2 flex items-center gap-2 text-xs text-text-muted">
            <span>
              {t('health.liveness')}:{' '}
              <strong className="text-text-primary">
                {t(info.live ? 'health.probePassing' : 'health.probeFailing')}
              </strong>
            </span>
            <span>
              {t('health.readiness')}:{' '}
              <strong className="text-text-primary">
                {t(info.ready ? 'health.probePassing' : 'health.probeFailing')}
              </strong>
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border pt-2.5">
        <span className="flex items-center gap-1.5 text-xs text-text-muted">
          <Icon size={11} style={{ color: cfg.iconColor }} /> {t('health.probesLabel')}
        </span>
        <span className="flex items-center gap-1.5">
          {/* A port is a number the reader may copy: LTR, always. */}
          {info.port && (
            <span dir="ltr" className="rounded-md bg-bg-tertiary px-1.5 py-0.5 font-mono text-xs text-text-muted [unicode-bidi:isolate]">
              :{info.port}
            </span>
          )}
          {/* The question a failing probe raises is always "what is it
              saying?", and the answer is one screen away. Offered on every
              card so the route is learned before it is needed. */}
          <DeepLink link={logsLinkForService(name)} />
        </span>
      </div>
    </motion.div>
  )
}

export default memo(ServiceCard)
