'use client'

import { useState } from 'react'
import { ThumbsUp, ThumbsDown, BarChart2, ShieldCheck, Shield, ShieldAlert } from 'lucide-react'
import Modal from '@/components/ui/Modal'

function Section({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-border last:border-b-0 pb-4 last:pb-0 mb-4 last:mb-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center justify-between w-full text-left text-[15px] font-semibold text-text-primary py-2 hover:text-accent transition-colors"
      >
        {title}
        <span className="text-text-muted text-[13px] font-normal">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && <div className="mt-2 text-[15px] text-text-secondary space-y-2">{children}</div>}
    </div>
  )
}

function PreBlock({ label, content }) {
  if (!content) return null
  return (
    <div>
      {label && <div className="text-[13px] font-medium text-text-muted mb-1">{label}</div>}
      <pre className="p-3 rounded-lg bg-bg-tertiary border border-border text-[13px] overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
        {content}
      </pre>
    </div>
  )
}

export default function MessageMetricsModal({ open, onOpenChange, message }) {
  const isUser = message?.sender === 'You' || message?.sender === 'User'
  const meta = message?.metadata || {}
  const hasMetadata = isUser
    ? meta.historySent != null || message?.text
    : meta.sources?.length || meta.promptSent || meta.chunks?.length ||
      meta.rerankScores?.length || meta.evaluation

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Message Details & Metrics" size="lg">
      <div className="space-y-4">
        {!hasMetadata ? (
          <p className="text-text-muted text-[15px]">No metrics available for this message.</p>
        ) : isUser ? (
          <>
            <Section title="Question sent">
              <PreBlock label="Your question (as sent to the backend)" content={message?.text} />
            </Section>
            <Section title="Conversation history included">
              <PreBlock
                label="History sent with this question"
                content={meta.historySent || '(none)'}
              />
            </Section>
          </>
        ) : (
          <>
            <Section title="Full prompt sent to LLM">
              <PreBlock content={meta.promptSent} />
            </Section>

            <Section title="RAG context (chunks used)">
              {meta.chunks?.length ? (
                <div className="space-y-3">
                  {meta.chunks.map((chunk, i) => (
                    <div key={i} className="p-3 rounded-lg bg-bg-tertiary border border-border">
                      <div className="text-[13px] text-text-muted mb-1">Chunk {i + 1}</div>
                      <div className="text-[15px] whitespace-pre-wrap break-words">{chunk}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-text-muted text-[15px]">
                  {meta.retrievalBypassed ? 'Retrieval was bypassed (general knowledge query).' : 'No chunks retrieved.'}
                </p>
              )}
            </Section>

            <Section title="Sources (files and chunks)">
              {meta.sources?.length ? (
                <div className="space-y-3">
                  {meta.sources.map((src, i) => (
                    <div
                      key={i}
                      className="p-3 rounded-lg bg-bg-tertiary border border-border space-y-2"
                    >
                      <div className="flex flex-wrap gap-2 text-[13px]">
                        {src.filename && (
                          <span className="px-2 py-0.5 rounded bg-accent/20 text-accent">
                            {src.filename}
                          </span>
                        )}
                        {src.similarity != null && (
                          <span className="text-text-muted">
                            Similarity: {(src.similarity * 100).toFixed(1)}%
                          </span>
                        )}
                        {src.chunk_index != null && (
                          <span className="text-text-muted">Chunk #{src.chunk_index}</span>
                        )}
                      </div>
                      <div className="text-[15px] whitespace-pre-wrap break-words line-clamp-4">
                        {typeof src === 'string' ? src : src.text}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-text-muted text-[15px]">No sources.</p>
              )}
            </Section>

            {meta.rerankScores?.length > 0 && (
              <Section title="Reranker scores">
                <div className="space-y-1.5">
                  {meta.rerankScores.map((item, i) => {
                    const score = typeof item === 'object' ? (item.score ?? item.rerank_score) : item
                    const filename = typeof item === 'object' ? (item.filename ?? item.file_name) : null
                    const pct = score != null ? (score * 100).toFixed(1) : null
                    const barColor =
                      score >= 0.75 ? 'bg-success' :
                      score >= 0.50 ? 'bg-warning' : 'bg-text-muted'
                    return (
                      <div key={i} className="flex items-center gap-2">
                        <BarChart2 size={12} className="shrink-0 text-text-muted" />
                        <span className="truncate text-[13px] text-text-secondary flex-1 min-w-0">
                          {filename ?? `Result ${i + 1}`}
                        </span>
                        {pct != null && (
                          <>
                            <div className="w-20 h-1.5 rounded-full bg-bg-tertiary overflow-hidden shrink-0">
                              <div
                                className={`h-full rounded-full ${barColor}`}
                                style={{ width: `${Math.min(parseFloat(pct), 100)}%` }}
                              />
                            </div>
                            <span className="text-[13px] font-medium text-text-secondary w-10 text-right shrink-0">
                              {pct}%
                            </span>
                          </>
                        )}
                      </div>
                    )
                  })}
                </div>
              </Section>
            )}

            {meta.evaluation && (
              <Section title="Answer quality">
                <div className="grid grid-cols-3 gap-3 text-[15px] mb-3">
                  {meta.evaluation.retrieval_score != null && (
                    <div className="p-2 rounded-lg bg-bg-tertiary text-center">
                      <div className="text-text-muted text-[13px] mb-0.5">Retrieval</div>
                      <div className="font-semibold">
                        {(meta.evaluation.retrieval_score * 100).toFixed(0)}%
                      </div>
                    </div>
                  )}
                  {meta.evaluation.coverage_score != null && (
                    <div className="p-2 rounded-lg bg-bg-tertiary text-center">
                      <div className="text-text-muted text-[13px] mb-0.5">Coverage</div>
                      <div className="font-semibold">
                        {(meta.evaluation.coverage_score * 100).toFixed(0)}%
                      </div>
                    </div>
                  )}
                  {meta.evaluation.confidence_level && (
                    <div className="p-2 rounded-lg bg-bg-tertiary text-center">
                      <div className="text-text-muted text-[13px] mb-0.5">Confidence</div>
                      <div className={`font-semibold flex items-center justify-center gap-1
                        ${meta.evaluation.confidence_level === 'high'   ? 'text-success' :
                          meta.evaluation.confidence_level === 'medium' ? 'text-warning'  : 'text-danger'}`}
                      >
                        {meta.evaluation.confidence_level === 'high'   && <ShieldCheck size={13} />}
                        {meta.evaluation.confidence_level === 'medium' && <Shield size={13} />}
                        {meta.evaluation.confidence_level === 'low'    && <ShieldAlert size={13} />}
                        {meta.evaluation.confidence_level.charAt(0).toUpperCase() +
                          meta.evaluation.confidence_level.slice(1)}
                      </div>
                    </div>
                  )}
                </div>
                <p className="text-text-muted text-[13px]">
                  Metrics computed locally — no extra LLM call. Retrieval = mean top-3 rerank scores.
                  Coverage = answer/context token overlap.
                </p>
              </Section>
            )}

            <Section title="Metrics">
              <div className="grid grid-cols-2 gap-3 text-[15px]">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <div className="text-text-muted text-[13px]">Retrieval bypassed</div>
                  <div>{meta.retrievalBypassed ? 'Yes' : 'No'}</div>
                </div>
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <div className="text-text-muted text-[13px]">Search results count</div>
                  <div>{meta.searchResultsCount ?? '-'}</div>
                </div>
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <div className="text-text-muted text-[13px]">Top similarity</div>
                  <div>
                    {meta.topSimilarity != null
                      ? `${(meta.topSimilarity * 100).toFixed(1)}%`
                      : '-'}
                  </div>
                </div>
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <div className="text-text-muted text-[13px]">Chunks used</div>
                  <div>{meta.chunks?.length ?? meta.sources?.length ?? 0}</div>
                </div>
              </div>
            </Section>

            <Section title="Rate this response" defaultOpen={false}>
              <div className="flex gap-4 items-center">
                <span className="text-text-muted text-[15px]">Was this helpful?</span>
                <button
                  type="button"
                  className="p-2 rounded-lg border border-border hover:bg-bg-tertiary hover:border-accent transition-colors"
                  title="Good"
                >
                  <ThumbsUp size={18} className="text-text-secondary" />
                </button>
                <button
                  type="button"
                  className="p-2 rounded-lg border border-border hover:bg-bg-tertiary hover:border-danger transition-colors"
                  title="Poor"
                >
                  <ThumbsDown size={18} className="text-text-secondary" />
                </button>
              </div>
              <textarea
                placeholder="Optional notes..."
                className="mt-3 w-full p-3 rounded-lg bg-bg-tertiary border border-border text-[15px] resize-none h-20 focus:outline-none focus:ring-2 focus:ring-accent/50"
                readOnly
              />
            </Section>
          </>
        )}
      </div>
    </Modal>
  )
}
