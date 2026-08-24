/**
 * ModelSelector — compact card for choosing which model to use.
 */
'use client'

import { useMemo } from 'react'
import { Cpu } from 'lucide-react'
import Select, { SelectItem } from '@/components/ui/Select'

export default function ModelSelector({ models, selectedModel, defaultModel, onSelectModel }) {
  const modelOptions = useMemo(() => {
    if (models.length === 0) {
      return [{ name: `${defaultModel} (default)`, value: defaultModel }]
    }
    return models.map((model) => {
      const name = typeof model === 'object' ? model.name || model.id || JSON.stringify(model) : String(model)
      const value = typeof model === 'object' ? model.name || model.id || String(model) : String(model)
      return { name, value }
    })
  }, [models, defaultModel])

  return (
    <div className="rounded-2xl border border-border bg-bg-elevated p-3 shadow-sm">
      <div className="mb-2.5 flex items-center gap-2 px-0.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft text-primary">
          <Cpu size={13} />
        </span>
        <div className="min-w-0">
          <div className="text-[13px] font-semibold text-text-primary">Response model</div>
          <div className="text-xs text-text-muted">Used for this conversation</div>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Select
          id="model-select"
          value={String(selectedModel || defaultModel)}
          onValueChange={onSelectModel}
          placeholder="Select model"
          className="h-9 w-full text-[13px]"
          aria-label="Select LLM model"
        >
          {modelOptions.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.name}
            </SelectItem>
          ))}
        </Select>

        {models.length === 0 && (
          <p className="rounded-lg bg-warning-soft px-2.5 py-2 text-xs leading-relaxed text-warning">
            Model list unavailable. Using {defaultModel}.
          </p>
        )}
      </div>
    </div>
  )
}
