'use client'

import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

const Input = forwardRef(function Input(
  {
    label,
    error,
    hint,
    icon: Icon,
    rightElement,
    size = 'md',
    className = '',
    containerClassName = '',
    style = {},
    disabled = false,
    ...props
  },
  ref
) {
  const sizeClasses = {
    sm: 'h-8 text-xs px-2.5',
    md: 'h-9 text-sm px-3',
    lg: 'h-10 text-sm px-3.5',
  }

  const iconPad = Icon ? (size === 'sm' ? 'pl-7' : 'pl-9') : ''

  return (
    <div className={cn('flex flex-col gap-1', containerClassName)}>
      {label && (
        <label
          className="text-xs font-medium"
          style={{ color: 'var(--fg-muted)' }}
        >
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        {Icon && (
          <Icon
            size={size === 'sm' ? 13 : 15}
            className="absolute left-2.5 pointer-events-none shrink-0"
            style={{ color: 'var(--fg-soft)' }}
          />
        )}
        <input
          ref={ref}
          disabled={disabled}
          className={cn(
            'w-full rounded-lg border outline-none transition-all duration-150',
            'placeholder:text-[var(--fg-soft)]',
            'focus:ring-2 focus:ring-[var(--ring)] focus:border-[var(--border-focus)]',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            sizeClasses[size] || sizeClasses.md,
            iconPad,
            rightElement ? 'pr-10' : '',
            error ? 'border-[var(--danger)] focus:ring-[rgba(239,68,68,0.25)]' : '',
            className
          )}
          style={{
            background:  'var(--surface)',
            color:       'var(--fg)',
            borderColor: error ? 'var(--danger)' : 'var(--border)',
            ...style,
          }}
          {...props}
        />
        {rightElement && (
          <div className="absolute right-2.5 flex items-center">
            {rightElement}
          </div>
        )}
      </div>
      {error && (
        <p className="text-[11px]" style={{ color: 'var(--danger)' }}>
          {error}
        </p>
      )}
      {hint && !error && (
        <p className="text-[11px]" style={{ color: 'var(--fg-soft)' }}>
          {hint}
        </p>
      )}
    </div>
  )
})

export default Input

/** Textarea variant with the same styling conventions */
export const Textarea = forwardRef(function Textarea(
  { label, error, hint, className = '', containerClassName = '', ...props },
  ref
) {
  return (
    <div className={cn('flex flex-col gap-1', containerClassName)}>
      {label && (
        <label className="text-xs font-medium" style={{ color: 'var(--fg-muted)' }}>
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        className={cn(
          'w-full rounded-lg border px-3 py-2 text-sm outline-none resize-y transition-all duration-150',
          'placeholder:text-[var(--fg-soft)]',
          'focus:ring-2 focus:ring-[var(--ring)] focus:border-[var(--border-focus)]',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          error ? 'border-[var(--danger)]' : '',
          className
        )}
        style={{
          background:  'var(--surface)',
          color:       'var(--fg)',
          borderColor: error ? 'var(--danger)' : 'var(--border)',
        }}
        {...props}
      />
      {error && (
        <p className="text-[11px]" style={{ color: 'var(--danger)' }}>{error}</p>
      )}
      {hint && !error && (
        <p className="text-[11px]" style={{ color: 'var(--fg-soft)' }}>{hint}</p>
      )}
    </div>
  )
})
