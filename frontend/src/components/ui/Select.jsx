'use client'

import * as SelectPrimitive from '@radix-ui/react-select'
import { ChevronDown, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function Select({
  value,
  onValueChange,
  placeholder = 'Select…',
  // What the closed trigger shows. Left undefined, Radix mirrors the
  // selected item's own content — which is right for a one-line option and
  // wrong for a rich one, where the trigger would grow a second line and a
  // badge. Passing a node here keeps the trigger a single compact row.
  valueLabel,
  children,
  className = '',
  disabled = false,
  ...props
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrimitive.Trigger
        className={cn(
          'inline-flex items-center justify-between gap-2 w-full px-3 py-2 rounded-lg text-[15px] font-medium',
          'border outline-hidden transition-all duration-150',
          'focus:ring-2 focus:ring-[var(--ring)] focus:border-[var(--border-focus)]',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          className
        )}
        style={{
          background:  'var(--surface)',
          color:       'var(--fg)',
          borderColor: 'var(--border)',
        }}
        onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-strong)'}
        onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
        {...props}
      >
        <SelectPrimitive.Value placeholder={
          <span style={{ color: 'var(--fg-soft)' }}>{placeholder}</span>
        }>
          {valueLabel}
        </SelectPrimitive.Value>
        <SelectPrimitive.Icon>
          <ChevronDown size={14} style={{ color: 'var(--fg-soft)' }} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>

      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className="overflow-hidden rounded-xl z-[9999] animate-fade-in"
          style={{
            background:  'var(--surface-elevated)',
            border:      '1px solid var(--border)',
            boxShadow:   'var(--shadow-lg)',
            minWidth:    'var(--radix-select-trigger-width)',
          }}
          position="popper"
          sideOffset={4}
        >
          <SelectPrimitive.Viewport className="p-1">
            {children}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}

export function SelectItem({ value, children, textValue, className = '' }) {
  return (
    <SelectPrimitive.Item
      value={value}
      // Radix reads an option's text off its children for type-ahead. A rich
      // option — a name, a badge and a summary line — has none it can read,
      // so the plain name is passed explicitly rather than losing keyboard
      // type-ahead on exactly the options that need it most.
      textValue={textValue}
      className={cn(
        'relative flex items-center justify-between px-3 py-2 rounded-md text-[15px] font-medium outline-hidden cursor-pointer select-none',
        'transition-colors duration-100',
        className
      )}
      style={{ color: 'var(--fg-muted)' }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--fg)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--fg-muted)' }}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator>
        <Check size={13} style={{ color: 'var(--primary)' }} />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  )
}

export function SelectGroup({ label, children }) {
  return (
    <SelectPrimitive.Group>
      {label && (
        <SelectPrimitive.Label className="px-3 py-1.5 label-xs">
          {label}
        </SelectPrimitive.Label>
      )}
      {children}
    </SelectPrimitive.Group>
  )
}
