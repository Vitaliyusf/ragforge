/** Error boundary */
'use client'

import { AlertTriangle } from 'lucide-react'
import Button from '@/components/ui/Button'

export default function Error({ error, reset }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg-primary text-text-primary p-8">
      <div className="flex flex-col items-center max-w-md text-center">
        <div className="w-20 h-20 rounded-2xl bg-danger-soft flex items-center justify-center mb-6">
          <AlertTriangle className="text-danger" size={40} />
        </div>
        <h2 className="text-2xl font-semibold mb-2">Something went wrong</h2>
        <p className="text-text-secondary mb-8">
          {error?.message || 'An unexpected error occurred. Please try again.'}
        </p>
        <Button variant="primary" onClick={reset} size="lg">
          Try again
        </Button>
      </div>
    </div>
  )
}
