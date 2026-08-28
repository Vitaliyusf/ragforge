'use client'

import { RedactedBlock, Empty } from './shared'

/**
 * What the model was given to work from: the assembled passage context, the
 * conversation history that travelled with the question, and any rewritten
 * query. All of it can echo private documents, so all of it starts hidden.
 */
export default function ContextSection({ debugPayloads = {}, historySent }) {
  const blocks = [
    { label: 'Retrieved context', content: debugPayloads.generation_context },
    { label: 'Conversation history sent', content: historySent },
    { label: 'Query rewrite', content: debugPayloads.rewrite_response },
    { label: 'Generation instructions', content: debugPayloads.generation_instructions },
  ].filter((block) => block.content != null && block.content !== '')

  if (!blocks.length) {
    return <Empty label="No context payloads for this turn" />
  }

  return (
    <div className="space-y-2">
      {blocks.map((block) => (
        <RedactedBlock key={block.label} label={block.label} content={block.content} />
      ))}
    </div>
  )
}
