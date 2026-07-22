/** Settings route */
'use client'

import ConfigTab from '@/features/config/components/ConfigTab'

export default function Settings() {
  return (
    <div className="min-h-screen bg-bg-primary text-text-primary p-7">
      <ConfigTab />
    </div>
  )
}
