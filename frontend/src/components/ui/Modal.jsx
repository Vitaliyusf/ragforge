'use client'

import { useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

const MODAL_Z = 2147483647

function getSizeClass(size, variant) {
  if (variant === 'drawer') {
    if (size === 'lg') return 'max-w-2xl'
    if (size === 'xl') return 'max-w-3xl'
    return 'max-w-xl'
  }
  if (size === 'sm')  return 'max-w-sm'
  if (size === 'lg')  return 'max-w-2xl'
  if (size === 'xl')  return 'max-w-4xl'
  return 'max-w-lg'
}

export default function Modal({
  open,
  onOpenChange,
  title,
  description,
  descriptionIcon,
  children,
  showClose = true,
  size = 'default',
  variant = 'modal',
}) {
  const [container, setContainer] = useState(null)
  useEffect(() => {
    setContainer(typeof document !== 'undefined' ? document.body : null)
  }, [])

  const sizeClass = getSizeClass(size, variant)

  // Radix links `aria-describedby` to a `Dialog.Description` if one is
  // rendered, and warns when it is not. A dialog whose body is a form or a
  // table has no one-line description to give, so the attribute is removed
  // explicitly instead of pointing at an element that does not exist.
  const describedBy = description ? undefined : { 'aria-describedby': undefined }

  const descriptionBlock = description ? (
    <div className="mb-4 flex gap-3">
      {descriptionIcon}
      <Dialog.Description
        className="text-[15px] leading-relaxed"
        style={{ color: 'var(--fg-muted)' }}
      >
        {description}
      </Dialog.Description>
    </div>
  ) : null

  const sharedContentStyle = {
    background: 'var(--surface-elevated)',
    border:     '1px solid var(--border)',
    boxShadow:  'var(--shadow-xl)',
  }

  const CloseButton = () => (
    <Dialog.Close asChild>
      <button
        className={cn(
          'rounded-lg p-2 transition-colors outline-hidden',
          'focus-visible:ring-2 focus-visible:ring-[var(--ring)]'
        )}
        style={{ color: 'var(--fg-soft)' }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--fg)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--fg-soft)' }}
        aria-label="Close"
      >
        <X size={18} />
      </button>
    </Dialog.Close>
  )

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal container={container ?? undefined}>
        <Dialog.Overlay
          className="modal-overlay fixed inset-0 backdrop-blur-xs"
          style={{ background: 'rgba(0,0,0,0.6)', zIndex: MODAL_Z }}
        />

        {variant === 'drawer' ? (
          <Dialog.Content
            className="drawer-content fixed inset-y-0 right-0 flex w-full justify-end p-3"
            style={{ zIndex: MODAL_Z + 1 }}
            {...describedBy}
          >
            <div
              className={cn('flex h-full w-full flex-col overflow-hidden rounded-2xl', sizeClass)}
              style={sharedContentStyle}
            >
              <div
                className="flex items-center justify-between px-5 py-4 border-b"
                style={{ borderColor: 'var(--border)' }}
              >
                <Dialog.Title className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>
                  {title}
                </Dialog.Title>
                {showClose && <CloseButton />}
              </div>
              <div className="flex-1 overflow-y-auto p-5">
                {descriptionBlock}
                {children}
              </div>
            </div>
          </Dialog.Content>
        ) : (
          <div
            className="pointer-events-none fixed inset-0 flex items-center justify-center overflow-auto p-4"
            style={{ zIndex: MODAL_Z + 1 }}
          >
            <Dialog.Content
              className={cn(
                'modal-content pointer-events-auto my-auto max-h-[90vh] w-full overflow-y-auto rounded-2xl',
                sizeClass
              )}
              style={sharedContentStyle}
              {...describedBy}
            >
              <div className="p-5">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <Dialog.Title className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>
                    {title}
                  </Dialog.Title>
                  {showClose && <CloseButton />}
                </div>
                {descriptionBlock}
                {children}
              </div>
            </Dialog.Content>
          </div>
        )}
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function ConfirmModal({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel  = 'Cancel',
  onConfirm,
  variant = 'primary',
  loading = false,
}) {
  const handleConfirm = async () => {
    await onConfirm?.()
    onOpenChange(false)
  }

  // The confirm and cancel controls suppress the UA outline to carry the
  // app's own ring, so the ring has to be spelled out — an `outline-hidden`
  // with no `focus-visible` replacement leaves a keyboard user with no way to
  // tell which of two buttons, one of them destructive, is about to fire.
  const focusRing =
    'focus:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)] ' +
    'focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface-elevated)]'

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      descriptionIcon={
        variant === 'danger' ? (
          <AlertTriangle
            size={18}
            className="shrink-0 mt-0.5"
            style={{ color: 'var(--warning)' }}
            aria-hidden="true"
          />
        ) : null
      }
      showClose={!loading}
      size="sm"
    >
      <div className="flex justify-end gap-2">
        <Dialog.Close asChild>
          <button
            type="button"
            disabled={loading}
            className={cn(
              'px-4 py-2 rounded-lg text-[15px] font-medium transition-colors',
              'disabled:opacity-60 disabled:cursor-not-allowed',
              focusRing
            )}
            style={{ background: 'var(--surface-hover)', color: 'var(--fg-muted)' }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-active)'}
            onMouseLeave={e => e.currentTarget.style.background = 'var(--surface-hover)'}
          >
            {cancelLabel}
          </button>
        </Dialog.Close>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={loading}
          className={cn(
            'px-4 py-2 rounded-lg text-[15px] font-medium text-white transition-colors',
            'disabled:opacity-60 disabled:cursor-not-allowed',
            focusRing
          )}
          style={{
            background: variant === 'danger' ? 'var(--danger)' : 'var(--primary)',
          }}
          onMouseEnter={e => e.currentTarget.style.filter = 'brightness(1.1)'}
          onMouseLeave={e => e.currentTarget.style.filter = ''}
        >
          {loading ? 'Working…' : confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
