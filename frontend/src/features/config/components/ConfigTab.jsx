'use client'

import { useState, useEffect } from 'react'
import { Settings, Cpu, Sliders, Database, Clock } from 'lucide-react'
import { toast } from 'sonner'
import { configService } from '@/features/config'
import { modelService } from '@/features/models'
import { config as appConfig } from '@/lib/config'
import Card from '@/components/ui/Card'
import PageHeader from '@/components/ui/PageHeader'

const formFieldClass = 'w-full px-4 py-2.5 rounded-xl bg-bg-tertiary border border-border text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg-primary disabled:opacity-60'
const labelClass = 'block text-text-secondary text-sm mb-2'

export default function ConfigTab() {
  const [config, setConfig] = useState(null)
  const [generationParams, setGenerationParams] = useState(null)
  const [modelConfigs, setModelConfigs] = useState(null)
  const [implementations, setImplementations] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadAllConfig()
  }, [])

  const loadAllConfig = async () => {
    try {
      setLoading(true)
      const [configData, paramsData, modelData, implData] = await Promise.all([
        configService.getConfig(),
        configService.getGenerationParams(),
        configService.getModelConfigs(),
        modelService.getImplementations()
      ])
      setConfig(configData)
      setGenerationParams(paramsData)
      setModelConfigs(modelData)
      if (implData.implementations) {
        setImplementations(implData.implementations)
      }
    } catch (err) {
      toast.error('Failed to load configuration', { description: err.message })
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateConfig = async (updates) => {
    try {
      setLoading(true)
      const result = await configService.updateConfig(updates)
      toast.success(result.message || 'Configuration updated')
      await loadAllConfig()
    } catch (err) {
      toast.error('Update failed', { description: err.message })
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateGenerationParams = async (params) => {
    try {
      setLoading(true)
      await configService.updateGenerationParams(params)
      toast.success('Generation parameters updated')
      await loadAllConfig()
    } catch (err) {
      toast.error('Update failed', { description: err.message })
    } finally {
      setLoading(false)
    }
  }

  const handleSwitchImplementation = async (implementation) => {
    try {
      setLoading(true)
      const result = await configService.switchImplementation(implementation)
      toast.success(result.message || `Switched to ${implementation}`)
      await loadAllConfig()
    } catch (err) {
      console.error('Failed to switch implementation:', err)
      toast.error('Switch failed', { description: err.message || err })
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateModelConfigs = async (updates) => {
    try {
      setLoading(true)
      await configService.updateModelConfigs(updates)
      toast.success('Model configurations updated')
      await loadAllConfig()
    } catch (err) {
      toast.error('Update failed', { description: err.message })
    } finally {
      setLoading(false)
    }
  }

  if (loading && !config) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted">Loading configuration...</div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-6xl overflow-y-auto p-3 text-text-primary md:p-6">
      <PageHeader
        title="Configuration"
        description="Manage LLM backend, model settings, generation parameters, and timeouts."
        icon={Settings}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card variant="elevated" className="p-6">
          <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
            <Cpu size={18} />
            LLM Implementation
          </h2>
          <div className="mb-4">
            <label className={labelClass}>
              Current: {config?.llm_implementation || 'N/A'}
            </label>
            <select
              value={config?.llm_implementation || ''}
              onChange={(e) => handleSwitchImplementation(e.target.value)}
              disabled={loading}
              className={`${formFieldClass} cursor-pointer`}
            >
              {implementations.map((impl) => (
                <option key={impl.name} value={impl.name}>
                  {impl.display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="mb-4">
            <label className={labelClass}>Device</label>
            <select
              value={config?.device || 'auto'}
              onChange={(e) => handleUpdateConfig({ device: e.target.value })}
              disabled={loading}
              className={`${formFieldClass} cursor-pointer`}
            >
              <option value="auto">Auto</option>
              <option value="cuda">CUDA (GPU)</option>
              <option value="cpu">CPU</option>
              <option value="mps">MPS (Apple Silicon)</option>
            </select>
          </div>
          <div>
            <label className={labelClass}>Max Concurrent Requests</label>
            <input
              type="number"
              value={config?.max_concurrent_requests || 10}
              onChange={(e) => handleUpdateConfig({ max_concurrent_requests: parseInt(e.target.value) })}
              disabled={loading}
              min="1"
              max="100"
              className={formFieldClass}
            />
          </div>
        </Card>

        <Card variant="elevated" className="p-6">
          <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
            <Settings size={18} />
            Model Configurations
          </h2>
          
          {modelConfigs && (
            <div className="flex flex-col gap-3">
              {['summary_model', 'metadata_model', 'rag_chat_model', 'default_model'].map((key) => (
                <div key={key}>
                  <label className={labelClass}>
                    {key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                  </label>
                  <input
                    type="text"
                    value={modelConfigs[key] || ''}
                    onChange={(e) => setModelConfigs({ ...modelConfigs, [key]: e.target.value })}
                    onBlur={() => handleUpdateModelConfigs({ [key]: modelConfigs[key] })}
                    className={formFieldClass}
                  />
                </div>
              ))}
            </div>
          )}
        </Card>

        {generationParams?.huggingface && (
          <Card variant="elevated" className="p-6">
            <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
              <Sliders size={18} />
              Hugging Face Parameters
            </h2>
            
            <div className="flex flex-col gap-3">
              <div>
                <label className={labelClass}>
                  Max Length: {generationParams.huggingface.max_length}
                </label>
                <input
                  type="range"
                  min="64"
                  max="2048"
                  step="64"
                  value={generationParams.huggingface.max_length}
                  onChange={(e) => {
                    const newParams = {
                      ...generationParams,
                      huggingface: { ...generationParams.huggingface, max_length: parseInt(e.target.value) }
                    }
                    setGenerationParams(newParams)
                    handleUpdateGenerationParams({ huggingface: newParams.huggingface })
                  }}
                  className="w-full accent-accent"
                />
              </div>
              <div>
                <label className={labelClass}>
                  Temperature: {generationParams.huggingface.temperature.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={generationParams.huggingface.temperature}
                  onChange={(e) => {
                    const newParams = {
                      ...generationParams,
                      huggingface: { ...generationParams.huggingface, temperature: parseFloat(e.target.value) }
                    }
                    setGenerationParams(newParams)
                    handleUpdateGenerationParams({ huggingface: newParams.huggingface })
                  }}
                  className="w-full accent-accent"
                />
              </div>
              <div>
                <label className={labelClass}>
                  Top P: {generationParams.huggingface.top_p.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={generationParams.huggingface.top_p}
                  onChange={(e) => {
                    const newParams = {
                      ...generationParams,
                      huggingface: { ...generationParams.huggingface, top_p: parseFloat(e.target.value) }
                    }
                    setGenerationParams(newParams)
                    handleUpdateGenerationParams({ huggingface: newParams.huggingface })
                  }}
                  className="w-full accent-accent"
                />
              </div>
              <label className="flex items-center gap-2 text-text-secondary text-[13px] cursor-pointer">
                <input
                  type="checkbox"
                  checked={generationParams.huggingface.do_sample}
                  onChange={(e) => {
                    const newParams = {
                      ...generationParams,
                      huggingface: { ...generationParams.huggingface, do_sample: e.target.checked }
                    }
                    setGenerationParams(newParams)
                    handleUpdateGenerationParams({ huggingface: newParams.huggingface })
                  }}
                />
                Do Sample
              </label>
            </div>
          </Card>
        )}

        {generationParams?.vllm && (
          <Card variant="elevated" className="p-6">
            <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
              <Sliders size={18} />
              vLLM Parameters
            </h2>
            
            <div className="flex flex-col gap-3">
              <div>
                <label className={labelClass}>Base URL</label>
                <input
                  type="text"
                  value={config?.vllm?.base_url || generationParams.vllm.base_url || appConfig.vllmBaseUrl}
                  onChange={(e) => {
                    setConfig({ ...config, vllm: { ...(config?.vllm || {}), base_url: e.target.value } })
                  }}
                  onBlur={() => handleUpdateConfig({ vllm: { base_url: config?.vllm?.base_url || generationParams.vllm.base_url } })}
                  className={formFieldClass}
                />
              </div>
              {[
                { key: 'max_tokens', min: 64, max: 2048, step: 64, parse: parseInt, fmt: (v) => v },
                { key: 'temperature', min: 0, max: 2, step: 0.1, parse: parseFloat, fmt: (v) => v.toFixed(2) },
                { key: 'top_p', min: 0, max: 1, step: 0.05, parse: parseFloat, fmt: (v) => v.toFixed(2) },
                { key: 'top_k', min: 1, max: 100, step: 1, parse: parseInt, fmt: (v) => v }
              ].map(({ key, min, max, step, parse, fmt }) => (
                <div key={key}>
                  <label className={labelClass}>
                    {key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}: {fmt(generationParams.vllm[key])}
                  </label>
                  <input
                    type="range"
                    min={min}
                    max={max}
                    step={step}
                    value={generationParams.vllm[key]}
                    onChange={(e) => {
                      const newParams = {
                        ...generationParams,
                        vllm: { ...generationParams.vllm, [key]: parse(e.target.value) }
                      }
                      setGenerationParams(newParams)
                      handleUpdateGenerationParams({ vllm: newParams.vllm })
                    }}
                    className="w-full accent-accent"
                  />
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card variant="elevated" className="p-6">
          <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
            <Database size={18} />
            Ollama Configuration
          </h2>
          <div className="flex flex-col gap-3">
            <div>
              <label className={labelClass}>Ollama Base URL</label>
              <input
                type="text"
                value={config?.ollama_url || 'http://host.docker.internal:11434'}
                onChange={(e) => setConfig({ ...config, ollama_url: e.target.value })}
                onBlur={() => handleUpdateConfig({ ollama_url: config?.ollama_url })}
                className={formFieldClass}
                placeholder="http://host.docker.internal:11434"
              />
            </div>
            <div className="p-3 rounded-lg bg-bg-tertiary text-xs text-text-muted">
              <strong className="text-text-secondary">Note:</strong> Ollama must be running and accessible at the specified URL.
              Make sure Ollama is installed and running on your system.
            </div>
          </div>
        </Card>

        <Card variant="elevated" className="p-6">
          <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
            <Clock size={18} />
            Timeout Settings
          </h2>
          <div className="flex flex-col gap-3">
            {[
              { key: 'llm_timeout', min: 10, max: 300, step: 10, default: 60 },
              { key: 'summary_timeout', min: 30, max: 600, step: 30, default: 120 },
              { key: 'metadata_timeout', min: 10, max: 300, step: 10, default: 60 }
            ].map(({ key, min, max, step, default: def }) => (
              <div key={key}>
                <label className={labelClass}>
                  {key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())} (seconds): {config?.[key] || def}
                </label>
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={step}
                  value={config?.[key] || def}
                  onChange={(e) => setConfig({ ...config, [key]: parseFloat(e.target.value) })}
                  onMouseUp={() => handleUpdateConfig({ [key]: config?.[key] })}
                  className="w-full accent-accent"
                />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
