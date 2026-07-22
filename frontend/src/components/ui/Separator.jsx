'use client'

import { cn } from '@/lib/utils'

export default function Separator({ orientation = 'horizontal', className = '' }) {
  return (
    <div
      className={cn(
        orientation === 'vertical' ? 'w-px h-full' : 'h-px w-full',
        className
      )}
      style={{ background: 'var(--border)' }}
      role="separator"
      aria-orientation={orientation}
    />
  )
}
