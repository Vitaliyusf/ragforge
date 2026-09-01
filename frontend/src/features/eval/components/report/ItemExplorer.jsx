'use client'

import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import Select, { SelectItem } from '@/components/ui/Select'
import { EMPTY, UNSCORABLE_ITEM_NOTE_KEY, formatCount, formatPercent } from '@/features/metrics/components/metricsConfig'
import { SCORE_BANDS, failureLabel, filterItems } from '../../runReport'
import { Cell, Note, Num, ReportTable, Row } from './primitives'
import { useI18n } from '@/i18n'

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
  const { t } = useI18n()
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
    return <Note>{emptyNote || t('evalReport.runKeptNoItems')}</Note>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          size="sm"
          icon={Search}
          value={search}
          placeholder={t('evalReport.searchPlaceholder')}
          aria-label={t('evalReport.searchItems')}
          // An item id is technical and a question may be Hebrew: the box
          // follows whatever the reader types.
          dir="auto"
          containerClassName="min-w-[200px] grow sm:grow-0"
          onChange={(event) => change(setSearch)(event.target.value)}
        />
        <Select
          value={band}
          onValueChange={change(setBand)}
          className="w-[180px]"
          aria-label={t('evalReport.scoreBand')}
        >
          {SCORE_BANDS.map((option) => (
            <SelectItem key={option.id} value={option.id}>
              {t(option.labelKey)}
            </SelectItem>
          ))}
        </Select>
        <Button
          variant={failuresOnly ? 'secondary' : 'ghost'}
          size="sm"
          aria-pressed={failuresOnly}
          onClick={() => change(setFailuresOnly)(!failuresOnly)}
        >
          {t('evalReport.failuresOnly')}
        </Button>
        <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {t('evalReport.filteredItems', {
            shown: formatCount(filtered.length),
            total: formatCount(items.length),
          })}
        </span>
      </div>

      {filtered.length === 0 ? (
        <Note>{t('evalReport.noItemMatch')}</Note>
      ) : (
        <>
          <ReportTable
            caption={t('evalReport.itemsCaption')}
            columns={[
              { key: 'query', label: t('evalReport.query') },
              { key: 'rank', label: t('evalReport.firstHit'), align: 'right' },
              // Recall@10 is a metric name and stays canonical.
              { key: 'recall', label: 'Recall@10', align: 'right' },
              { key: 'lost', label: t('evalReport.lostAt') },
              { key: 'expected', label: t('evalReport.expected') },
              { key: 'retrieved', label: t('evalReport.retrieved') },
            ]}
          >
            {page.map((row) => (
              <Row key={row.item_id}>
                {/* The question is the reader's own text; the item id under
                    it is an identifier. */}
                <th
                  scope="row"
                  dir="auto"
                  className="py-1.5 pe-3 text-start font-normal"
                  style={{ color: 'var(--fg)' }}
                >
                  {row.query}
                  <span className="block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                    {row.item_id}
                  </span>
                  {row.error && (
                    <span className="text-[12px]" style={{ color: 'var(--danger)' }}>
                      {t('evalReport.itemFailed', { error: row.error })}
                    </span>
                  )}
                  {row.skipped && !row.error && (
                    <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                      {t('evalReport.notLabelled')}
                    </span>
                  )}
                  {row.unscorable && !row.error && (
                    <span className="text-[12px]" style={{ color: 'var(--warning)' }}>
                      {t(UNSCORABLE_ITEM_NOTE_KEY)}
                    </span>
                  )}
                </th>
                <Num>{row.first_hit_rank ?? EMPTY}</Num>
                <Num>{formatPercent(row.recall_at_10)}</Num>
                <Cell>{failureLabel(row, t)}</Cell>
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
                {t('evalReport.showMore')}
              </Button>
              <span className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                {t('evalReport.showingMatching', {
                  shown: formatCount(page.length),
                  total: formatCount(filtered.length),
                })}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
