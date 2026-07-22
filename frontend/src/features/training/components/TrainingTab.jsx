'use client'

import { useState, useRef, useCallback } from 'react'
import {
  Upload,
  Play,
  Square,
  Trash2,
  Database,
  Cpu,
  Layers,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  Settings2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { useTraining } from '../hooks/useTraining'

const STATUS_STYLES = {
  queued: 'text-blue-400 bg-blue-400/10',
  preparing: 'text-amber-400 bg-amber-400/10',
  training: 'text-violet-400 bg-violet-400/10',
  saving: 'text-cyan-400 bg-cyan-400/10',
  completed: 'text-emerald-400 bg-emerald-400/10',
  failed: 'text-red-400 bg-red-400/10',
  cancelled: 'text-text-muted bg-bg-tertiary',
}

function DatasetUploadForm({ onUpload }) {
  const fileRef = useRef(null)
  const [name, setName] = useState('')
  const [format, setFormat] = useState('instruction')
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  const handleUpload = async (file) => {
    if (!file || !name.trim()) return
    setUploading(true)
    try {
      await onUpload(file, name.trim(), format)
      setName('')
      if (fileRef.current) fileRef.current.value = ''
    } catch (err) {
      console.error('Upload failed:', err)
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file && fileRef.current) {
      const dt = new DataTransfer()
      dt.items.add(file)
      fileRef.current.files = dt.files
    }
  }, [])

  return (
    <div className="space-y-3">
      <div
        className={`relative border-2 border-dashed rounded-xl p-6 text-center transition-colors ${
          dragOver ? 'border-accent bg-accent/5' : 'border-border hover:border-border-hover'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <Upload size={24} className="mx-auto mb-2 text-text-muted" />
        <p className="text-sm text-text-secondary mb-1">
          Drag & drop a JSONL or CSV file
        </p>
        <p className="text-xs text-text-muted mb-3">
          or click to browse
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".jsonl,.json,.csv"
          className="absolute inset-0 opacity-0 cursor-pointer"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Dataset name..."
          className="px-3 py-2 rounded-lg bg-bg-tertiary border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          className="px-3 py-2 rounded-lg bg-bg-tertiary border border-border text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="instruction">Instruction (instruction/input/output)</option>
          <option value="conversational">Conversational (messages)</option>
        </select>
      </div>
      <Button
        variant="primary"
        size="sm"
        onClick={() => fileRef.current?.files[0] && handleUpload(fileRef.current.files[0])}
        disabled={uploading || !name.trim()}
        className="w-full gap-1.5"
      >
        {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
        {uploading ? 'Uploading...' : 'Upload Dataset'}
      </Button>
    </div>
  )
}

function TrainingConfigForm({ onStart, disabled }) {
  const [datasetId, setDatasetId] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [config, setConfig] = useState({
    lora_r: 16,
    lora_alpha: 32,
    learning_rate: 0.0002,
    num_epochs: 3,
    batch_size: 4,
    max_seq_length: 1024,
  })

  const updateConfig = (key, value) => setConfig((prev) => ({ ...prev, [key]: value }))

  return (
    <div className="space-y-3">
      <input
        type="text"
        value={datasetId}
        onChange={(e) => setDatasetId(e.target.value)}
        placeholder="Dataset ID to train on..."
        className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent"
      />

      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors"
      >
        <Settings2 size={12} />
        Advanced Config
        {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {showAdvanced && (
        <div className="grid grid-cols-2 gap-2 p-3 rounded-lg bg-bg-tertiary/50 border border-border/50">
          {[
            { key: 'lora_r', label: 'LoRA Rank', type: 'number' },
            { key: 'lora_alpha', label: 'LoRA Alpha', type: 'number' },
            { key: 'learning_rate', label: 'Learning Rate', type: 'number', step: '0.0001' },
            { key: 'num_epochs', label: 'Epochs', type: 'number' },
            { key: 'batch_size', label: 'Batch Size', type: 'number' },
            { key: 'max_seq_length', label: 'Max Seq Length', type: 'number' },
          ].map(({ key, label, type, step }) => (
            <div key={key}>
              <label className="text-[11px] text-text-muted">{label}</label>
              <input
                type={type}
                value={config[key]}
                onChange={(e) => updateConfig(key, type === 'number' ? Number(e.target.value) : e.target.value)}
                step={step}
                className="w-full px-2 py-1.5 rounded-md bg-bg-primary border border-border text-xs text-text-primary font-mono focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          ))}
        </div>
      )}

      <Button
        variant="primary"
        size="sm"
        onClick={() => onStart(datasetId, config)}
        disabled={disabled || !datasetId.trim()}
        className="w-full gap-1.5"
      >
        <Play size={14} />
        Start Training
      </Button>
    </div>
  )
}

function JobProgressBar({ job }) {
  const progress = job.progress || {}
  const pct = progress.total_steps > 0
    ? Math.round((progress.current_step / progress.total_steps) * 100)
    : 0

  return (
    <div className="p-4 rounded-xl bg-violet-400/5 border border-violet-400/20">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Loader2 size={14} className="text-violet-400 animate-spin" />
          <span className="text-sm font-medium text-text-primary">
            Training in Progress
          </span>
        </div>
      </div>
      <div className="h-2 rounded-full bg-bg-tertiary overflow-hidden mb-2">
        <div
          className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="grid grid-cols-4 gap-2 text-[11px]">
        <div>
          <span className="text-text-muted">Step</span>
          <div className="font-mono text-text-primary">{progress.current_step || 0}/{progress.total_steps || '?'}</div>
        </div>
        <div>
          <span className="text-text-muted">Epoch</span>
          <div className="font-mono text-text-primary">{(progress.current_epoch || 0).toFixed(1)}</div>
        </div>
        <div>
          <span className="text-text-muted">Loss</span>
          <div className="font-mono text-text-primary">{progress.loss != null ? progress.loss.toFixed(4) : '-'}</div>
        </div>
        <div>
          <span className="text-text-muted">ETA</span>
          <div className="font-mono text-text-primary">
            {progress.eta_seconds != null ? `${Math.round(progress.eta_seconds)}s` : '-'}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function TrainingTab() {
  const {
    datasets,
    jobs,
    adapters,
    activeJob,
    loading,
    error,
    uploadDataset,
    deleteDataset,
    startTraining,
    cancelJob,
    deleteAdapter,
    refresh,
  } = useTraining()

  return (
    <div className="mx-auto flex h-full w-full max-w-6xl flex-col gap-4 overflow-y-auto p-3 md:p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-violet-400/10">
            <Cpu size={20} className="text-violet-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-text-primary">QLoRA Fine-Tuning</h2>
            <p className="text-xs text-text-muted">
              4-bit quantized LoRA adapter training
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={refresh} className="gap-1.5">
          <RefreshCw size={14} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-400/10 border border-red-400/30 text-red-400 text-sm">
          <AlertTriangle size={14} className="inline mr-2" />
          {error}
        </div>
      )}

      {/* Active Job Progress */}
      {activeJob && activeJob.status === 'training' && (
        <div className="space-y-2">
          <JobProgressBar job={activeJob} />
          <Button variant="secondary" size="sm" onClick={() => cancelJob(activeJob.job_id)} className="gap-1.5">
            <Square size={14} />
            Cancel Training
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Dataset Upload */}
        <Card variant="glass" className="p-4">
          <div className="flex items-center gap-2 mb-4">
            <Database size={16} className="text-text-secondary" />
            <h3 className="text-sm font-semibold text-text-primary">Datasets</h3>
            <span className="text-[11px] text-text-muted">({datasets.length})</span>
          </div>
          <DatasetUploadForm onUpload={uploadDataset} />
          {datasets.length > 0 && (
            <div className="mt-4 space-y-2">
              {datasets.map((ds) => (
                <div key={ds.dataset_id} className="flex items-center justify-between p-2.5 rounded-lg bg-bg-tertiary/50 border border-border/50">
                  <div>
                    <div className="text-sm font-medium text-text-primary">{ds.name}</div>
                    <div className="text-[11px] text-text-muted">
                      {ds.stats?.total_rows || 0} rows | {ds.format}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      ds.status === 'validated' ? 'text-emerald-400 bg-emerald-400/10' : 'text-red-400 bg-red-400/10'
                    }`}>{ds.status}</span>
                    <button onClick={() => deleteDataset(ds.dataset_id)} className="text-text-muted hover:text-red-400 transition-colors">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Start Training */}
        <Card variant="glass" className="p-4">
          <div className="flex items-center gap-2 mb-4">
            <Play size={16} className="text-text-secondary" />
            <h3 className="text-sm font-semibold text-text-primary">Start Training</h3>
          </div>
          <TrainingConfigForm
            onStart={startTraining}
            disabled={!!activeJob}
          />
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Job History */}
        <Card variant="glass" className="p-4">
          <div className="flex items-center gap-2 mb-4">
            <Clock size={16} className="text-text-secondary" />
            <h3 className="text-sm font-semibold text-text-primary">Job History</h3>
            <span className="text-[11px] text-text-muted">({jobs.length})</span>
          </div>
          {jobs.length === 0 ? (
            <div className="text-center py-6 text-text-muted text-sm">No training jobs yet</div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {jobs.map((job) => (
                <div key={job.job_id} className="p-3 rounded-lg bg-bg-tertiary/50 border border-border/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${STATUS_STYLES[job.status] || ''}`}>
                      {job.status}
                    </span>
                  </div>
                  {job.progress?.loss != null && (
                    <div className="text-[11px] text-text-secondary">
                      Loss: {job.progress.loss.toFixed(4)} | Steps: {job.progress.current_step}/{job.progress.total_steps}
                    </div>
                  )}
                  {job.error_message && (
                    <div className="text-[11px] text-red-400 mt-1 truncate">{job.error_message}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Adapters */}
        <Card variant="glass" className="p-4">
          <div className="flex items-center gap-2 mb-4">
            <Layers size={16} className="text-text-secondary" />
            <h3 className="text-sm font-semibold text-text-primary">LoRA Adapters</h3>
            <span className="text-[11px] text-text-muted">({adapters.length})</span>
          </div>
          {adapters.length === 0 ? (
            <div className="text-center py-6 text-text-muted text-sm">No adapters yet</div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {adapters.map((adapter) => (
                <div key={adapter.adapter_id} className="flex items-center justify-between p-3 rounded-lg bg-bg-tertiary/50 border border-border/50">
                  <div>
                    <div className="text-xs font-medium text-text-primary">{adapter.base_model?.split('/').pop()}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      adapter.loaded ? 'text-emerald-400 bg-emerald-400/10' : 'text-text-muted bg-bg-tertiary'
                    }`}>
                      {adapter.loaded ? 'Loaded' : 'Available'}
                    </span>
                    <button onClick={() => deleteAdapter(adapter.adapter_id)} className="text-text-muted hover:text-red-400 transition-colors">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
