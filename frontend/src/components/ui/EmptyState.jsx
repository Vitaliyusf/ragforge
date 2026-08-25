'use client'

import { cn } from '@/lib/utils'

/**
 * Premium empty state component with icon, title, description, and optional CTA.
 */
export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  size = 'md',
  className = '',
}) {
  const sizes = {
    sm: { iconSize: 28, iconBox: 'w-12 h-12', titleClass: 'text-[15px]', descClass: 'text-[13px]' },
    md: { iconSize: 36, iconBox: 'w-16 h-16', titleClass: 'text-lg', descClass: 'text-[15px]' },
    lg: { iconSize: 48, iconBox: 'w-20 h-20', titleClass: 'text-xl', descClass: 'text-[15px]' },
  }
  const { iconSize, iconBox, titleClass, descClass } = sizes[size] || sizes.md

  return (
    <div className={cn('flex flex-col items-center justify-center text-center py-16 px-6 gap-5', className)}>
      {Icon && (
        <div className="relative">
          {/* Glow ring */}
          <div
            className={cn('rounded-2xl flex items-center justify-center', iconBox)}
            style={{
              background: 'var(--primary-soft)',
              boxShadow:  '0 0 0 8px var(--primary-soft), 0 0 0 16px rgba(var(--primary-rgb, 34 211 197) / 0.04)',
            }}
          >
            <Icon size={iconSize} strokeWidth={1.5} style={{ color: 'var(--primary)' }} className="animate-float" />
          </div>
        </div>
      )}
      <div className="space-y-2 max-w-xs">
        <h3 className={cn('font-semibold', titleClass)} style={{ color: 'var(--fg)' }}>
          {title}
        </h3>
        {description && (
          <p className={cn('leading-relaxed', descClass)} style={{ color: 'var(--fg-muted)' }}>
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
