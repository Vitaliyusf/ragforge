'use client'

import { useEffect, useRef, useState } from 'react'
import { MoreHorizontal, Trash2, Upload } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import { ConfirmModal } from '@/components/ui/Modal'
import Select, { SelectItem } from '@/components/ui/Select'
import {
  EMPTY,
  formatCount,
  formatFingerprint,
  formatTimestamp,
} from '@/features/metrics/components/metricsConfig'

/**
 * Which dataset the run will score, and what is in it.
 *
 * One row, because that is all this is: a selector and four facts about the
 * selection. The destructive action is behind an overflow menu rather than
 * sitting beside the metrics, where it had been one mis-click from deleting
 * a hand-labelled dataset.
 */
export default function EvalSetupCard({
  datasets = [],
  datasetId,
  dataset,
  busy,
  running,
  onSelect,
  onImport,
  onDelete,
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const fingerprint = dataset?.dataset_sha256

  return (
    <Card padding="sm">
      <CardHeader
        className="mb-3"
        title="Evaluation setup"
        description="Scored against hand-labelled ground truth, not live traffic."
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={onImport}
              leftIcon={<Upload size={13} />}
            >
              Import
            </Button>
            <DatasetActions
              disabled={busy || running || !datasetId}
              onDelete={() => setConfirmDelete(true)}
            />
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <Select
          value={datasetId}
          onValueChange={onSelect}
          className="w-full sm:w-[248px]"
          aria-label="Golden set"
        >
          {datasets.map((entry) => (
            <SelectItem key={entry.dataset_id} value={entry.dataset_id}>
              {entry.name}
            </SelectItem>
          ))}
        </Select>

        <dl className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-3">
          <Fact label="Items" value={formatCount(dataset?.item_count)} />
          <Fact
            label="Version"
            value={dataset?.dataset_version ? `v${dataset.dataset_version}` : EMPTY}
          />
          <Fact
            label="Fingerprint"
            value={
              fingerprint ? (
                // Twelve characters tell two label sets apart by eye; the
                // whole digest stays in the title so it can still be copied.
                <code className="tabular-nums" title={fingerprint}>
                  {formatFingerprint(fingerprint)}
                </code>
              ) : (
                EMPTY
              )
            }
          />
          <Fact
            label="Last run"
            value={dataset?.last_run_at ? formatTimestamp(dataset.last_run_at) : EMPTY}
          />
        </dl>
      </div>

      <ConfirmModal
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this golden set?"
        description={
          `${dataset?.name || 'This dataset'} and its ${formatCount(dataset?.item_count)} ` +
          'hand-labelled items are removed for this workspace. Runs already ' +
          'recorded against it keep their own snapshot of the labels they scored.'
        }
        confirmLabel="Delete golden set"
        variant="danger"
        onConfirm={() => onDelete?.(datasetId)}
      />
    </Card>
  )
}

/** One piece of dataset metadata. Deliberately not a full row each. */
function Fact({ label, value }) {
  return (
    <div className="min-w-0">
      <dt className="label-xs">{label}</dt>
      <dd className="mt-0.5 truncate text-[15px] font-semibold tabular-nums">{value}</dd>
    </div>
  )
}

/**
 * The dataset's secondary actions.
 *
 * Closes on Escape and on a click outside, like the workspace settings menu
 * in the header — the same behaviour, so the two menus are not two different
 * things to learn.
 */
function DatasetActions({ disabled, onDelete }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const outside = (event) => {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false)
    }
    const keys = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', outside)
    document.addEventListener('keydown', keys)
    return () => {
      document.removeEventListener('mousedown', outside)
      document.removeEventListener('keydown', keys)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Dataset actions"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        <MoreHorizontal size={15} />
      </Button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-1.5 w-52 overflow-hidden rounded-xl border p-1"
          style={{
            background: 'var(--surface-elevated)',
            borderColor: 'var(--border)',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onDelete()
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition-colors hover:bg-[var(--danger-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
            style={{ color: 'var(--danger)' }}
          >
            <Trash2 size={13} />
            Delete golden set
          </button>
        </div>
      )}
    </div>
  )
}
