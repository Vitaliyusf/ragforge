'use client'

import { RedactedBlock, Empty } from './shared'
import { useI18n } from '@/i18n'

/**
 * What the model was given to work from: the assembled passage context, the
 * conversation history that travelled with the question, and any rewritten
 * query. All of it can echo private documents, so all of it starts hidden.
 */
export default function ContextSection({ debugPayloads = {}, historySent }) {
  const { t } = useI18n()
  const blocks = [
    { label: t('inspector.retrievedContext'), content: debugPayloads.generation_context },
    { label: t('inspector.historySent'), content: historySent },
    { label: t('inspector.queryRewrite'), content: debugPayloads.rewrite_response },
    { label: t('inspector.generationInstructions'), content: debugPayloads.generation_instructions },
  ].filter((block) => block.content != null && block.content !== '')

  if (!blocks.length) {
    return <Empty label={t('inspector.emptyContext')} />
  }

  return (
    <div className="space-y-2">
      {blocks.map((block) => (
        <RedactedBlock key={block.label} label={block.label} content={block.content} />
      ))}
    </div>
  )
}
