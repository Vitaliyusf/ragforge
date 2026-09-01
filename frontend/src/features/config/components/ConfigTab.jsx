'use client'

import { useCallback, useEffect, useState } from 'react'
import { Clock, Cpu, Database, Settings, Sliders } from 'lucide-react'
import { notifyCritical } from '@/lib/notify'

import Card from '@/components/ui/Card'
import PageHeader from '@/components/ui/PageHeader'
import { configService } from '@/features/config'
import { useI18n } from '@/i18n'
import { techLtrProps } from '@/lib/accessibility/direction'

const labelClass = 'text-[13px] text-text-muted'
// `text-end`, not `text-right`: the value column follows the interface
// direction, while the value *inside* it stays LTR because every one of
// these is a URL, a model id or a number an operator may copy.
const valueClass = 'break-all text-end text-[13px] font-medium text-text-primary'

function ValueRow({ label, value }) {
  const { t } = useI18n()
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border py-2.5 last:border-b-0">
      <dt className={labelClass}>{label}</dt>
      <dd {...techLtrProps()} className={valueClass}>{value ?? t('settings.notSet')}</dd>
    </div>
  )
}

function ConfigCard({ icon: Icon, title, children }) {
  return (
    <Card variant="elevated" className="p-6">
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
        <Icon size={18} />
        {title}
      </h2>
      <dl>{children}</dl>
    </Card>
  )
}

export default function ConfigTab() {
  const { t } = useI18n()
  const [config, setConfig] = useState(null)

  // Without the config payload this tab has nothing to render, so a load
  // failure is blocking rather than routine: it stays up, and it carries the
  // retry instead of asking the user to reload the page.
  const loadConfig = useCallback(() => {
    configService.getConfig().then(setConfig).catch((error) => {
      notifyCritical(t('settings.unavailable'), { error, onRetry: loadConfig })
    })
  }, [t])

  useEffect(() => { loadConfig() }, [loadConfig])

  if (!config) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted">
        {t('settings.loading')}
      </div>
    )
  }

  const generation = config.generation_params || {}
  const huggingface = generation.huggingface || {}
  const vllmGeneration = generation.vllm || {}
  const models = config.models || {}
  const timeouts = config.timeouts || {}

  return (
    <div className="mx-auto w-full max-w-6xl overflow-y-auto p-3 text-text-primary md:p-6">
      <PageHeader
        title={t('settings.effectiveConfiguration')}
        description={t('settings.description')}
        icon={Settings}
      />

      <div className="mb-6 rounded-xl border border-border bg-bg-secondary p-4 text-[13px] text-text-secondary">
        <strong className="text-text-primary">{t('settings.deploymentOwned')}</strong>{' '}
        {t('settings.readOnly')} {t('settings.readOnlyDetail')}
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <ConfigCard icon={Cpu} title={t('settings.llmRuntime')}>
          <ValueRow label={t('settings.implementation')} value={config.llm_implementation} />
          <ValueRow label={t('settings.device')} value={config.device} />
          <ValueRow label={t('settings.maxConcurrentRequests')} value={config.max_concurrent_requests} />
          {/* Product names stay canonical; only the noun beside them is copy. */}
          <ValueRow label={`vLLM ${t('settings.baseUrl')}`} value={config.vllm?.base_url} />
          <ValueRow label={`vLLM ${t('settings.contextWindow')}`} value={config.vllm?.max_model_len} />
          <ValueRow label={`Ollama ${t('settings.baseUrl')}`} value={config.ollama_url} />
        </ConfigCard>

        <ConfigCard icon={Database} title={t('settings.models')}>
          <ValueRow label={t('settings.summary')} value={models.summary} />
          <ValueRow label={t('settings.metadata')} value={models.metadata} />
          <ValueRow label={t('settings.ragChat')} value={models.rag_chat} />
          <ValueRow label={t('settings.default')} value={models.default} />
        </ConfigCard>

        <ConfigCard icon={Sliders} title={t('settings.generationParameters')}>
          <ValueRow label={`HF ${t('settings.maxLength')}`} value={huggingface.max_length} />
          <ValueRow label={`HF ${t('settings.temperature')}`} value={huggingface.temperature} />
          <ValueRow label={`HF ${t('settings.topP')}`} value={huggingface.top_p} />
          <ValueRow
            label={`HF ${t('settings.sampling')}`}
            value={t(huggingface.do_sample ? 'settings.enabled' : 'settings.disabled')}
          />
          <ValueRow label={`vLLM ${t('settings.maxTokens')}`} value={vllmGeneration.max_tokens} />
          <ValueRow label={`vLLM ${t('settings.temperature')}`} value={vllmGeneration.temperature} />
          <ValueRow label={`vLLM ${t('settings.topP')}`} value={vllmGeneration.top_p} />
          <ValueRow label={`vLLM ${t('settings.topK')}`} value={vllmGeneration.top_k} />
        </ConfigCard>

        <ConfigCard icon={Clock} title={t('settings.timeouts')}>
          <ValueRow label="LLM" value={t('settings.seconds', { value: timeouts.llm })} />
          <ValueRow label={t('settings.summary')} value={t('settings.seconds', { value: timeouts.summary })} />
          <ValueRow label={t('settings.metadata')} value={t('settings.seconds', { value: timeouts.metadata })} />
        </ConfigCard>
      </div>
    </div>
  )
}
