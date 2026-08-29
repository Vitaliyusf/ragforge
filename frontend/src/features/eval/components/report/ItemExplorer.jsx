'use client'

import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import Select, { SelectItem } from '@/components/ui/Select'
import { EMPTY, UNSCORABLE_ITEM_NOTE, formatCount, formatPercent } from '@/features/metrics/components/metricsConfig'
import { SCORE_BANDS, failureLabel, filterItems } from '../../runReport'
import { Cell, Note, Num, ReportTable, Row } from './primitives'

/** How many rows are rendered at once. More arrive a page at a time. */
const PAGE = 50

/**
 * The per-item view: search, two filters, and the worst rows first.
 *
 * A golden set is thousands of rows long, and rendering all of them is how
 * this tab became the reason the page stuttered. The list is filtered and
 * sorted outside React (in `runReport`) and paged here, so the DOM holds a
 * screen's worth of rows however large the dataset is. The count above the
 * table always describes the whole filtered set, never the rendered page.
 */
export default function ItemExplorer({ items = [], emptyNote }) {
  const [search, setSearch] = useState('')
  const [failuresOnly, setFailuresOnly] = useState(false)
  const [band, setBand] = useState('all')
  const [shown, setShown] = useState(PAGE)

  const filtered = useMemo(
    () => filterItems(items, { search, failuresOnly, band }),
    [items, search, failuresOnly, band]
  )
  const page = filtered.slice(0, shown)

  const change = (apply) => (value) => {
    apply(value)
    setShown(PAGE)
  }

  if (!items.length) {
    return <Note>{emptyNote || 'This run kept no per-item rows.'}</Note>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          size="sm"
          icon={Search}
          value={search}
          placeholder="Search id or question"
          aria-label="Search items"
          containerClassName="min-w-[200px] grow sm:grow-0"
          onChange={(event) => change(setSearch)(event.target.value)}
        />
        <Select
          value={band}
          onValueChange={change(setBand)}
          className="w-[180px]"
          aria-label="Score band"
        >
          {SCORE_BANDS.map((option) => (
            <SelectItem key={option.id} value={option.id}>
              {option.label}
            </SelectItem>
          ))}
        </Select>
        <Button
          variant={failuresOnly ? 'secondary' : 'ghost'}
          size="sm"
          aria-pressed={failuresOnly}
          onClick={() => change(setFailuresOnly)(!failuresOnly)}
        >
          Failures only
        </Button>
        <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {formatCount(filtered.length)} of {formatCount(items.length)} items
        </span>
      </div>

      {filtered.length === 0 ? (
        <Note>No item matches these filters.</Note>
      ) : (
        <>
          <ReportTable
            caption="Per-item retrieval results, worst first"
            columns={[
              { key: 'query', label: 'Query' },
              { key: 'rank', label: 'First hit', align: 'right' },
              { key: 'recall', label: 'Recall@10', align: 'right' },
              { key: 'lost', label: 'Lost at' },
              { key: 'expected', label: 'Expected' },
              { key: 'retrieved', label: 'Retrieved' },
            ]}
          >
            {page.map((row) => (
              <Row key={row.item_id}>
                <th
                  scope="row"
                  className="py-1.5 pr-3 text-left font-normal"
                  style={{ color: 'var(--fg)' }}
                >
                  {row.query}
                  <span className="block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                    {row.item_id}
                  </span>
                  {row.error && (
                    <span className="text-[12px]" style={{ color: 'var(--danger)' }}>
                      failed: {row.error}
                    </span>
                  )}
                  {row.skipped && !row.error && (
                    <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                      not labelled — excluded from every average
                    </span>
                  )}
                  {row.unscorable && !row.error && (
                    <span className="text-[12px]" style={{ color: 'var(--warning)' }}>
                      {UNSCORABLE_ITEM_NOTE}
                    </span>
                  )}
                </th>
                <Num>{row.first_hit_rank ?? EMPTY}</Num>
                <Num>{formatPercent(row.recall_at_10)}</Num>
                <Cell>{failureLabel(row)}</Cell>
                <Cell className="font-mono text-[12px]" color="var(--fg-soft)">
                  {(row.expected_ids || []).join(', ') || EMPTY}
                </Cell>
                <Cell className="font-mono text-[12px]" color="var(--fg-soft)">
                  {(row.retrieved_ids || []).join(', ') || EMPTY}
                </Cell>
              </Row>
            ))}
          </ReportTable>

          {filtered.length > page.length && (
            <div className="flex items-center gap-3">
              <Button variant="secondary" size="sm" onClick={() => setShown(shown + PAGE)}>
                Show more
              </Button>
              <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                Showing {formatCount(page.length)} of {formatCount(filtered.length)} matching items.
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
