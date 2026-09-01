/** Error boundary */
'use client'

import { AlertTriangle } from 'lucide-react'
import Button from '@/components/ui/Button'
import { useI18n } from '@/i18n'

export default function Error({ error, reset }) {
  // This boundary renders above the provider when the tree below it fails,
  // so `useI18n` falls back to English rather than throwing.
  const { t } = useI18n()
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg-primary text-text-primary p-8">
      <div className="flex flex-col items-center max-w-md text-center">
        <div className="w-20 h-20 rounded-2xl bg-danger-soft flex items-center justify-center mb-6">
          <AlertTriangle className="text-danger" size={40} />
        </div>
        <h2 className="text-2xl font-semibold mb-2">{t('error.somethingWentWrong')}</h2>
        <p className="text-text-secondary mb-8">
          {error?.message || t('error.unexpected')}
        </p>
        <Button variant="primary" onClick={reset} size="lg">
          {t('common.tryAgain')}
        </Button>
      </div>
    </div>
  )
}
