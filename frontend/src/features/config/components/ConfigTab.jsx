'use client'

import { useCallback, useEffect, useState } from 'react'
import { Clock, Cpu, Database, Settings, Sliders } from 'lucide-react'
import { notifyCritical } from '@/lib/notify'

import Card from '@/components/ui/Card'
import PageHeader from '@/components/ui/PageHeader'
import { configService } from '@/features/config'

const labelClass = 'text-[13px] text-text-muted'
const valueClass = 'break-all text-right text-[13px] font-medium text-text-primary'

function ValueRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border py-2.5 last:border-b-0">
      <dt className={labelClass}>{label}</dt>
      <dd className={valueClass}>{value ?? 'Not set'}</dd>
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
  const [config, setConfig] = useState(null)

  // Without the config payload this tab has nothing to render, so a load
  // failure is blocking rather than routine: it stays up, and it carries the
  // retry instead of asking the user to reload the page.
  const loadConfig = useCallback(() => {
    configService.getConfig().then(setConfig).catch((error) => {
      notifyCritical('Configuration unavailable', { error, onRetry: loadConfig })
    })
  }, [])

  useEffect(() => { loadConfig() }, [loadConfig])

  if (!config) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted">
        Loading configuration...
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
        title="Effective configuration"
        description="Runtime settings loaded from the deployment environment."
        icon={Settings}
      />

      <div className="mb-6 rounded-xl border border-border bg-bg-secondary p-4 text-[13px] text-text-secondary">
        <strong className="text-text-primary">Deployment-owned:</strong> these values are read-only.
        Change the deployment environment or Compose configuration, then recreate or restart the
        affected service. No settings shown here are live-mutable.
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <ConfigCard icon={Cpu} title="LLM runtime">
          <ValueRow label="Implementation" value={config.llm_implementation} />
          <ValueRow label="Device" value={config.device} />
          <ValueRow label="Max concurrent requests" value={config.max_concurrent_requests} />
          <ValueRow label="vLLM base URL" value={config.vllm?.base_url} />
          <ValueRow label="vLLM context window" value={config.vllm?.max_model_len} />
          <ValueRow label="Ollama base URL" value={config.ollama_url} />
        </ConfigCard>

        <ConfigCard icon={Database} title="Models">
          <ValueRow label="Summary" value={models.summary} />
          <ValueRow label="Metadata" value={models.metadata} />
          <ValueRow label="RAG chat" value={models.rag_chat} />
          <ValueRow label="Default" value={models.default} />
        </ConfigCard>

        <ConfigCard icon={Sliders} title="Generation parameters">
          <ValueRow label="HF max length" value={huggingface.max_length} />
          <ValueRow label="HF temperature" value={huggingface.temperature} />
          <ValueRow label="HF top P" value={huggingface.top_p} />
          <ValueRow label="HF sampling" value={huggingface.do_sample ? 'Enabled' : 'Disabled'} />
          <ValueRow label="vLLM max tokens" value={vllmGeneration.max_tokens} />
          <ValueRow label="vLLM temperature" value={vllmGeneration.temperature} />
          <ValueRow label="vLLM top P" value={vllmGeneration.top_p} />
          <ValueRow label="vLLM top K" value={vllmGeneration.top_k} />
        </ConfigCard>

        <ConfigCard icon={Clock} title="Timeouts">
          <ValueRow label="LLM" value={`${timeouts.llm} seconds`} />
          <ValueRow label="Summary" value={`${timeouts.summary} seconds`} />
          <ValueRow label="Metadata" value={`${timeouts.metadata} seconds`} />
        </ConfigCard>
      </div>
    </div>
  )
}
