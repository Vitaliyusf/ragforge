'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Answer markdown.
 *
 * Prose inherits the surrounding direction so a Hebrew answer lays out
 * right-to-left, while code — which is technical text — is pinned to LTR so the
 * bidi algorithm cannot reorder its punctuation.
 */

const markdownComponents = {
  p:          ({ children }) => <p className="mb-2 leading-relaxed last:mb-0">{children}</p>,
  pre:        ({ children }) => <pre dir="ltr" className="my-2 overflow-x-auto rounded-xl bg-bg-tertiary p-3 text-[13px] font-mono">{children}</pre>,
  code:       ({ inline, children }) => inline
                ? <code dir="ltr" className="rounded bg-bg-tertiary px-1.5 py-0.5 font-mono text-[13px] text-accent [unicode-bidi:isolate]">{children}</code>
                : <code dir="ltr">{children}</code>,
  ul:         ({ children }) => <ul className="mb-2 list-disc space-y-0.5 ps-4">{children}</ul>,
  ol:         ({ children }) => <ol className="mb-2 list-decimal space-y-0.5 ps-4">{children}</ol>,
  li:         ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1:         ({ children }) => <h1 className="mb-1 text-lg font-bold">{children}</h1>,
  h2:         ({ children }) => <h2 className="mb-1 text-[15px] font-bold">{children}</h2>,
  h3:         ({ children }) => <h3 className="mb-1 text-[15px] font-semibold">{children}</h3>,
  blockquote: ({ children }) => <blockquote className="my-2 border-s-2 border-accent ps-3 italic text-text-muted">{children}</blockquote>,
  a:          ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2 hover:text-accent/80">{children}</a>,
  table:      ({ children }) => <div className="my-2 overflow-x-auto"><table className="w-full border-collapse text-[13px]">{children}</table></div>,
  th:         ({ children }) => <th className="border border-border bg-bg-tertiary px-2 py-1 text-start font-semibold">{children}</th>,
  td:         ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
  hr:         () => <hr className="my-3 border-border" />,
}

export default function MarkdownContent({ content }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  )
}
