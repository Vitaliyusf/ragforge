'use client'

import { cn } from '@/lib/utils'

export default function Switch({
  checked,
  onChange,
  label,
  disabled = false,
  size = 'md',
  className = '',
  id,
  ...props
}) {
  const sizes = {
    sm: { track: 'w-8 h-4',  thumb: 'w-3 h-3', travel: 'peer-checked:translate-x-4' },
    md: { track: 'w-10 h-5', thumb: 'w-4 h-4', travel: 'peer-checked:translate-x-5' },
    lg: { track: 'w-12 h-6', thumb: 'w-5 h-5', travel: 'peer-checked:translate-x-6' },
  }
  const s = sizes[size] || sizes.md

  return (
    <label
      className={cn(
        'inline-flex items-center gap-2',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
        className
      )}
    >
      <div className="relative">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange?.(e.target.checked)}
          disabled={disabled}
          className="sr-only peer"
          {...props}
        />
        {/* Track */}
        <div
          className={cn(
            s.track,
            'rounded-full border transition-all duration-200',
            'peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--ring)] peer-focus-visible:ring-offset-2',
          )}
          style={{
            background:   checked ? 'var(--primary)' : 'var(--surface-hover)',
            borderColor:  checked ? 'var(--primary)' : 'var(--border)',
            transition:   'all 200ms ease',
          }}
        />
        {/* Thumb */}
        <div
          className={cn(
            'absolute left-0.5 top-0.5 rounded-full shadow-sm',
            s.thumb,
            s.travel,
            'transition-transform duration-200'
          )}
          style={{
            background: checked ? 'var(--primary-fg, white)' : 'var(--fg-soft)',
            transform: `translateX(${checked ? (size === 'sm' ? '16px' : size === 'lg' ? '24px' : '20px') : '0'})`,
            transition: 'transform 200ms ease, background 200ms ease',
          }}
        />
      </div>
      {label && (
        <span className="text-[15px]" style={{ color: 'var(--fg-muted)' }}>
          {label}
        </span>
      )}
    </label>
  )
}
