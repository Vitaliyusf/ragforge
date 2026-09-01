/**
 * ModelSelector — compact card for choosing which model to use.
 */
'use client'

import { useMemo } from 'react'
import { Cpu } from 'lucide-react'
import Select, { SelectItem } from '@/components/ui/Select'
import { useI18n } from '@/i18n'

export default function ModelSelector({ models, selectedModel, defaultModel, onSelectModel }) {
  const { t } = useI18n()
  const modelOptions = useMemo(() => {
    if (models.length === 0) {
      return [{ name: t('chat.modelDefaultSuffix', { model: defaultModel }), value: defaultModel }]
    }
    return models.map((model) => {
      const name = typeof model === 'object' ? model.name || model.id || JSON.stringify(model) : String(model)
      const value = typeof model === 'object' ? model.name || model.id || String(model) : String(model)
      return { name, value }
    })
  }, [models, defaultModel, t])

  return (
    <div className="rounded-2xl border border-border bg-bg-elevated p-3 shadow-sm">
      <div className="mb-2.5 flex items-center gap-2 px-0.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft text-primary">
          <Cpu size={13} />
        </span>
        <div className="min-w-0">
          <div className="text-[13px] font-semibold text-text-primary">{t('chat.responseModel')}</div>
          <div className="text-xs text-text-muted">{t('chat.responseModelHint')}</div>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Select
          id="model-select"
          value={String(selectedModel || defaultModel)}
          onValueChange={onSelectModel}
          placeholder={t('chat.selectModel')}
          className="h-9 w-full text-[13px]"
          aria-label={t('chat.selectModelLabel')}
        >
          {/* A model name is a repository identifier: it stays LTR and
              isolated so a Hebrew menu cannot reorder its slashes and dots. */}
          {modelOptions.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              <span dir="ltr" className="inline-block [unicode-bidi:isolate]">{opt.name}</span>
            </SelectItem>
          ))}
        </Select>

        {models.length === 0 && (
          <p className="rounded-lg bg-warning-soft px-2.5 py-2 text-xs leading-relaxed text-warning">
            {t('chat.modelListUnavailable', { model: defaultModel })}
          </p>
        )}
      </div>
    </div>
  )
}
