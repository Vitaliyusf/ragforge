'use client'

import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  CheckCircle,
  Cpu,
  Download,
  HardDrive,
  Loader2,
  Package,
  RefreshCw,
  Search,
  Server,
  Sparkles,
  Zap,
} from 'lucide-react'
import { toast } from 'sonner'
import { modelService } from '@/features/models'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import Input from '@/components/ui/Input'
import PageHeader from '@/components/ui/PageHeader'

const safeRender = (value) => {
  if (value === null || value === undefined) return 'N/A'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const IMPL_ICONS = { vllm: Zap, huggingface: Cpu, ollama: Package }

function MetricTile({ icon: Icon, label, value, tone = 'primary', hint }) {
  const colors = {
    primary: { bg: 'var(--primary-soft)', color: 'var(--primary)' },
    success: { bg: 'var(--success-soft)', color: 'var(--success)' },
    info: { bg: 'var(--info-soft)', color: 'var(--info)' },
  }
  const style = colors[tone] || colors.primary

  return (
    <div className="flex items-center gap-3 rounded-2xl border border-border bg-bg-elevated p-3.5 shadow-sm">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: style.bg, color: style.color }}>
        <Icon size={17} />
      </span>
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-[0.09em] text-text-muted">{label}</div>
        <div className="mt-0.5 truncate text-lg font-semibold text-text-primary">{value}</div>
        {hint ? <div className="mt-0.5 truncate text-xs text-text-muted">{hint}</div> : null}
      </div>
    </div>
  )
}

export default function ModelManagementTab() {
  const [implementations, setImplementations] = useState([])
  const [selectedImplementation, setSelectedImplementation] = useState(null)
  const [implementationInfo, setImplementationInfo] = useState(null)
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState(null)
  const [modelInfo, setModelInfo] = useState(null)
  const [downloadStatus, setDownloadStatus] = useState({})
  const [modelQuery, setModelQuery] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadImplementations()
    loadModels()
  }, [])

  const loadImplementations = async () => {
    try {
      setLoading(true)
      const data = await modelService.getImplementations()
      if (data.implementations) {
        setImplementations(data.implementations)
        if (data.current) {
          setSelectedImplementation(data.current)
          loadImplementationInfo(data.current)
        }
      }
    } catch (err) {
      toast.error('Failed to load runtimes', { description: err.message })
    } finally {
      setLoading(false)
    }
  }

  const loadImplementationInfo = async (implementation) => {
    try {
      const info = await modelService.getImplementationInfo(implementation)
      setImplementationInfo(info)
    } catch (err) {
      console.error('Failed to load implementation info:', err)
    }
  }

  const loadModels = async () => {
    try {
      setLoading(true)
      const data = await modelService.listAllModels()
      if (data.models) setModels(data.models)
    } catch (err) {
      toast.error('Failed to load models', { description: err.message })
    } finally {
      setLoading(false)
    }
  }

  const handleImplementationChange = async (implementation) => {
    setSelectedImplementation(implementation)
    setImplementationInfo(null)
    await loadImplementationInfo(implementation)
  }

  const handleModelSelect = async (model) => {
    setSelectedModel(model)
    setModelInfo(null)
    try {
      const info = await modelService.getModelInfo(model.name || model)
      setModelInfo(info)
    } catch (err) {
      console.error('Failed to load model info:', err)
    }
  }

  const handleDownload = async (model, implementation) => {
    try {
      setLoading(true)
      await modelService.downloadModel(model, implementation)
      const pollStatus = setInterval(async () => {
        try {
          const status = await modelService.getDownloadStatus(model)
          setDownloadStatus((previous) => ({ ...previous, [model]: status }))
          if (status.status === 'completed' || status.status === 'error') {
            clearInterval(pollStatus)
            setLoading(false)
            if (status.status === 'completed') loadModels()
          }
        } catch (err) {
          clearInterval(pollStatus)
          setLoading(false)
        }
      }, 2000)
    } catch (err) {
      toast.error('Download failed', { description: err.message })
      setLoading(false)
    }
  }

  const filteredModels = useMemo(() => {
    const query = modelQuery.trim().toLocaleLowerCase()
    if (!query) return models
    return models.filter((model) => {
      const name = typeof model === 'string' ? model : model.name || model.id || ''
      return String(name).toLocaleLowerCase().includes(query)
    })
  }, [models, modelQuery])

  const downloadedCount = models.filter((model) => typeof model === 'object' && model.downloaded).length
  const activeImplementation = implementations.find((impl) => impl.name === selectedImplementation)

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-7xl flex-col overflow-y-auto p-3 md:p-6">
      <PageHeader
        title="Model workspace"
        description="Choose a runtime, inspect model availability, and manage local downloads."
        icon={Cpu}
        badge={selectedImplementation ? <Badge variant="primary" dot>{selectedImplementation}</Badge> : null}
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => { loadImplementations(); loadModels() }}
            disabled={loading}
            leftIcon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}
          >
            Refresh catalog
          </Button>
        }
      />

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricTile
          icon={Server}
          label="Active runtime"
          value={activeImplementation?.display_name || selectedImplementation || 'Not selected'}
          hint={`${implementations.length} runtime${implementations.length === 1 ? '' : 's'} available`}
        />
        <MetricTile
          icon={Package}
          label="Model catalog"
          value={models.length}
          hint={`${filteredModels.length} currently shown`}
          tone="info"
        />
        <MetricTile
          icon={HardDrive}
          label="Ready locally"
          value={downloadedCount}
          hint="Downloaded and available"
          tone="success"
        />
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(280px,0.72fr)_minmax(0,1.6fr)]">
        <Card variant="elevated" padding="none" className="h-fit">
          <div className="border-b border-border p-4">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-soft text-primary">
                <Server size={16} />
              </span>
              <div>
                <h2 className="text-[15px] font-semibold text-text-primary">Inference runtime</h2>
                <p className="mt-0.5 text-xs text-text-muted">Select the engine used to serve models.</p>
              </div>
            </div>
          </div>

          <div className="space-y-2 p-3">
            {implementations.map((implementation) => {
              const isActive = selectedImplementation === implementation.name
              const Icon = IMPL_ICONS[implementation.name?.toLowerCase()] || Cpu
              return (
                <motion.button
                  key={implementation.name}
                  whileTap={{ scale: 0.985 }}
                  onClick={() => handleImplementationChange(implementation.name)}
                  className="flex w-full items-center gap-3 rounded-xl border p-3 text-left outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-primary/40"
                  style={{
                    background: isActive ? 'var(--primary-soft)' : 'var(--surface-hover)',
                    borderColor: isActive ? 'var(--border-focus)' : 'var(--border)',
                    boxShadow: isActive ? '0 0 0 2px var(--ring)' : 'none',
                  }}
                >
                  <span
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
                    style={{ background: isActive ? 'var(--primary)' : 'var(--surface-active)', color: isActive ? 'white' : 'var(--fg-soft)' }}
                  >
                    <Icon size={16} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-semibold text-text-primary">{safeRender(implementation.display_name)}</span>
                    <span className="mt-0.5 block truncate text-xs text-text-muted">{safeRender(implementation.description)}</span>
                  </span>
                  {isActive ? <CheckCircle size={16} className="shrink-0 text-primary" /> : null}
                </motion.button>
              )
            })}

            {!loading && implementations.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-3 py-8 text-center text-[13px] text-text-muted">
                No runtimes are currently available.
              </div>
            ) : null}
          </div>

          <AnimatePresence>
            {implementationInfo?.features?.length > 0 ? (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden border-t border-border"
              >
                <div className="p-4">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-muted">
                    <Sparkles size={11} className="text-primary" /> Capabilities
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {implementationInfo.features.map((feature) => (
                      <Badge key={feature} variant="primary" size="xs">{feature}</Badge>
                    ))}
                  </div>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </Card>

        <Card variant="elevated" padding="none" className="flex min-h-[560px] flex-col">
          <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h2 className="text-[15px] font-semibold text-text-primary">Model catalog</h2>
                <Badge variant="default" size="xs">{filteredModels.length}</Badge>
              </div>
              <p className="mt-0.5 text-xs text-text-muted">Select a model to inspect its runtime details.</p>
            </div>
            <Input
              value={modelQuery}
              onChange={(event) => setModelQuery(event.target.value)}
              placeholder="Search models"
              icon={Search}
              size="sm"
              containerClassName="w-full sm:w-64"
            />
          </div>

          <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_280px]">
            <div className="min-h-0 overflow-y-auto p-3 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
              {loading && models.length === 0 ? (
                <div className="flex min-h-72 items-center justify-center">
                  <Loader2 size={24} className="animate-spin text-primary" />
                </div>
              ) : filteredModels.length === 0 ? (
                <div className="flex min-h-72 flex-col items-center justify-center text-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                    <Search size={19} />
                  </span>
                  <h3 className="mt-4 text-[15px] font-semibold text-text-primary">No matching models</h3>
                  <p className="mt-1 text-[13px] text-text-muted">Try a different name or refresh the catalog.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredModels.map((model, index) => {
                    const name = typeof model === 'string' ? model : model.name || model.id || 'Unknown'
                    const isSelected = selectedModel?.name === model.name || selectedModel === model
                    const isDownloaded = typeof model === 'object' && model.downloaded
                    const status = typeof model === 'object' ? model.status || 'available' : 'available'
                    const currentDownload = downloadStatus[name]

                    return (
                      <motion.button
                        type="button"
                        key={`${name}-${index}`}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: Math.min(index, 8) * 0.025 }}
                        onClick={() => handleModelSelect(model)}
                        className="flex w-full items-center gap-3 rounded-xl border p-3 text-left outline-none transition-all duration-200 hover:border-border-hover hover:bg-bg-tertiary focus-visible:ring-2 focus-visible:ring-primary/40"
                        style={{
                          background: isSelected ? 'var(--primary-soft)' : 'var(--surface-hover)',
                          borderColor: isSelected ? 'var(--border-focus)' : 'var(--border)',
                        }}
                      >
                        <span
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
                          style={{ background: isDownloaded ? 'var(--success-soft)' : 'var(--surface-active)', color: isDownloaded ? 'var(--success)' : 'var(--fg-soft)' }}
                        >
                          <Package size={15} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-semibold text-text-primary">{name}</span>
                          <span className="mt-0.5 block text-xs capitalize text-text-muted">
                            {currentDownload?.status ? `Download ${currentDownload.status}` : status}
                          </span>
                        </span>
                        <Badge variant={isDownloaded ? 'success' : isSelected ? 'primary' : 'default'} size="xs">
                          {isDownloaded ? 'Ready' : isSelected ? 'Selected' : 'Remote'}
                        </Badge>
                      </motion.button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="border-t border-border bg-bg-tertiary/30 p-4 xl:border-l xl:border-t-0">
              {selectedModel ? (
                <AnimatePresence mode="wait">
                  <motion.div
                    key={typeof selectedModel === 'string' ? selectedModel : selectedModel.name || selectedModel.id}
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                  >
                    <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                      <Package size={19} />
                    </div>
                    <div className="label-xs mb-1.5">Selected model</div>
                    <h3 className="break-words text-[15px] font-semibold text-text-primary">
                      {safeRender(modelInfo?.name || selectedModel?.name || selectedModel)}
                    </h3>
                    <div className="mt-4 space-y-2.5">
                      {[
                        ['Runtime', safeRender(modelInfo?.implementation || selectedImplementation)],
                        ['Status', safeRender(modelInfo?.status || selectedModel?.status || 'available')],
                        modelInfo?.downloaded !== undefined ? ['Local', modelInfo.downloaded ? 'Yes' : 'No'] : null,
                      ].filter(Boolean).map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between gap-3 border-b border-border/70 pb-2 text-[13px] last:border-0">
                          <span className="text-text-muted">{label}</span>
                          <span className="max-w-[65%] truncate font-medium text-text-primary">{value}</span>
                        </div>
                      ))}
                    </div>

                    {modelInfo && !modelInfo.downloaded ? (
                      <Button
                        variant="primary"
                        size="sm"
                        loading={loading}
                        onClick={() => {
                          const modelName = typeof modelInfo.name === 'object'
                            ? modelInfo.name?.name || modelInfo.name?.id || JSON.stringify(modelInfo.name)
                            : modelInfo.name || ''
                          handleDownload(modelName, selectedImplementation)
                        }}
                        disabled={loading}
                        className="mt-5 w-full"
                        leftIcon={<Download size={13} />}
                      >
                        Download model
                      </Button>
                    ) : null}
                  </motion.div>
                </AnimatePresence>
              ) : (
                <div className="flex min-h-64 flex-col items-center justify-center text-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-bg-tertiary text-text-muted">
                    <Package size={19} />
                  </span>
                  <h3 className="mt-4 text-[15px] font-semibold text-text-primary">Choose a model</h3>
                  <p className="mt-1 text-[13px] leading-relaxed text-text-muted">Details and download actions will appear here.</p>
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
