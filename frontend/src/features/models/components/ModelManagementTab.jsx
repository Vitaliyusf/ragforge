'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
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
import { notifyError, notifySuccess } from '@/lib/notify'
import { modelService } from '@/features/models'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import Input from '@/components/ui/Input'
import PageHeader from '@/components/ui/PageHeader'
import TechnicalText from '@/components/ui/TechnicalText'
import { useI18n } from '@/i18n'

/**
 * Whatever the runtime handed over, as something safe to put on screen.
 * `missing` is supplied by the caller so the placeholder can be localized
 * without this helper needing a locale of its own.
 */
const safeRender = (value, missing = 'N/A') => {
  if (value === null || value === undefined) return missing
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
  const { t } = useI18n()
  const [implementations, setImplementations] = useState([])
  const [selectedImplementation, setSelectedImplementation] = useState(null)
  const [implementationInfo, setImplementationInfo] = useState(null)
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState(null)
  const [modelInfo, setModelInfo] = useState(null)
  const [downloadStatus, setDownloadStatus] = useState({})
  const [modelQuery, setModelQuery] = useState('')
  const [loading, setLoading] = useState(false)
  // Download polls are started from a click handler, so they outlive no effect
  // of their own — they have to be cleared explicitly when the tab unmounts.
  const downloadPollsRef = useRef(new Set())

  useEffect(() => {
    loadImplementations()
    loadModels()
  }, [])

  useEffect(() => () => {
    downloadPollsRef.current.forEach(clearInterval)
    downloadPollsRef.current.clear()
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
      notifyError(t('models.loadRuntimesFailed'), { error: err, onRetry: loadImplementations })
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
      notifyError(t('models.loadModelsFailed'), { error: err, onRetry: loadModels })
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
      const stopPoll = () => {
        clearInterval(pollStatus)
        downloadPollsRef.current.delete(pollStatus)
      }
      const pollStatus = setInterval(async () => {
        try {
          const status = await modelService.getDownloadStatus(model)
          setDownloadStatus((previous) => ({ ...previous, [model]: status }))
          if (status.status === 'completed' || status.status === 'error') {
            stopPoll()
            setLoading(false)
            if (status.status === 'completed') {
              notifySuccess(t('models.downloaded', { model }))
              loadModels()
            }
          }
        } catch (err) {
          stopPoll()
          setLoading(false)
          notifyError(t('models.downloadStatusFailed'), {
            error: err,
            description: t('models.downloadStatusFailedDetail', { model }),
          })
        }
      }, 2000)
      downloadPollsRef.current.add(pollStatus)
    } catch (err) {
      notifyError(t('models.downloadFailed'), {
        error: err,
        onRetry: () => handleDownload(model, implementation),
      })
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
        title={t('models.workspace')}
        description={t('models.workspaceDescription')}
        icon={Cpu}
        badge={selectedImplementation
          ? <Badge variant="primary" dot><TechnicalText>{selectedImplementation}</TechnicalText></Badge>
          : null}
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => { loadImplementations(); loadModels() }}
            disabled={loading}
            leftIcon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}
          >
            {t('models.refreshCatalog')}
          </Button>
        }
      />

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricTile
          icon={Server}
          label={t('models.activeRuntime')}
          value={activeImplementation?.display_name || selectedImplementation || t('models.notSelected')}
          hint={t('models.runtimesAvailable', { count: implementations.length })}
        />
        <MetricTile
          icon={Package}
          label={t('models.catalog')}
          value={models.length}
          hint={t('models.currentlyShown', { count: filteredModels.length })}
          tone="info"
        />
        <MetricTile
          icon={HardDrive}
          label={t('models.readyLocally')}
          value={downloadedCount}
          hint={t('models.downloadedAvailable')}
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
                <h2 className="text-[15px] font-semibold text-text-primary">{t('models.inferenceRuntime')}</h2>
                <p className="mt-0.5 text-xs text-text-muted">{t('models.selectEngine')}</p>
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
                  className="flex w-full items-center gap-3 rounded-xl border p-3 text-start outline-hidden transition-all duration-200 focus-visible:ring-2"
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
                    {/* Runtime names and their descriptions come from the model
                        service and are canonical technology names. */}
                    <span className="block text-[15px] font-semibold text-text-primary">
                      {safeRender(implementation.display_name, t('models.notAvailableShort'))}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-text-muted">
                      {safeRender(implementation.description, t('models.notAvailableShort'))}
                    </span>
                  </span>
                  {isActive ? <CheckCircle size={16} className="shrink-0 text-primary" /> : null}
                </motion.button>
              )
            })}

            {!loading && implementations.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-3 py-8 text-center text-[13px] text-text-muted">
                {t('models.noRuntimes')}
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
                    <Sparkles size={11} className="text-primary" /> {t('models.capabilities')}
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
                <h2 className="text-[15px] font-semibold text-text-primary">{t('models.catalog')}</h2>
                <Badge variant="default" size="xs">{filteredModels.length}</Badge>
              </div>
              <p className="mt-0.5 text-xs text-text-muted">{t('models.catalogHint')}</p>
            </div>
            <Input
              value={modelQuery}
              onChange={(event) => setModelQuery(event.target.value)}
              placeholder={t('models.search')}
              aria-label={t('models.search')}
              dir="auto"
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
                  <h3 className="mt-4 text-[15px] font-semibold text-text-primary">{t('models.noMatches')}</h3>
                  <p className="mt-1 text-[13px] text-text-muted">{t('models.noMatchesDescription')}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredModels.map((model, index) => {
                    const name = typeof model === 'string' ? model : model.name || model.id || t('models.unknown')
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
                        className="flex w-full items-center gap-3 rounded-xl border p-3 text-start outline-hidden transition-all duration-200 hover:border-border-hover hover:bg-bg-tertiary focus-visible:ring-2"
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
                          {/* A model id is a repository slug: never reordered. */}
                          <TechnicalText className="block truncate text-[13px] font-semibold text-text-primary">
                            {name}
                          </TechnicalText>
                          <span className="mt-0.5 block text-xs capitalize text-text-muted">
                            {currentDownload?.status
                              ? t('models.downloadState', { status: currentDownload.status })
                              : status}
                          </span>
                        </span>
                        <Badge variant={isDownloaded ? 'success' : isSelected ? 'primary' : 'default'} size="xs">
                          {t(isDownloaded ? 'models.ready' : isSelected ? 'models.selected' : 'models.remote')}
                        </Badge>
                      </motion.button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="border-t border-border p-4 xl:border-s xl:border-t-0">
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
                    <div className="label-xs mb-1.5">{t('models.selectedModel')}</div>
                    <TechnicalText
                      as="h3"
                      className="break-words text-[15px] font-semibold text-text-primary"
                    >
                      {safeRender(
                        modelInfo?.name || selectedModel?.name || selectedModel,
                        t('models.notAvailableShort')
                      )}
                    </TechnicalText>
                    <div className="mt-4 space-y-2.5">
                      {[
                        [t('models.runtime'), safeRender(modelInfo?.implementation || selectedImplementation, t('models.notAvailableShort'))],
                        [t('models.status'), safeRender(modelInfo?.status || selectedModel?.status || 'available', t('models.notAvailableShort'))],
                        modelInfo?.downloaded !== undefined
                          ? [t('models.local'), t(modelInfo.downloaded ? 'models.yes' : 'models.no')]
                          : null,
                      ].filter(Boolean).map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between gap-3 border-b border-border pb-2 text-[13px] last:border-0">
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
                        {t('models.download')}
                      </Button>
                    ) : null}
                  </motion.div>
                </AnimatePresence>
              ) : (
                <div className="flex min-h-64 flex-col items-center justify-center text-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-bg-tertiary text-text-muted">
                    <Package size={19} />
                  </span>
                  <h3 className="mt-4 text-[15px] font-semibold text-text-primary">{t('models.chooseModel')}</h3>
                  <p className="mt-1 text-[13px] leading-relaxed text-text-muted">
                    {t('models.chooseModelDescription')}
                  </p>
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
