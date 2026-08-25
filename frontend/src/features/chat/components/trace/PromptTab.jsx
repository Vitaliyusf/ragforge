'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Empty } from './shared'

function PromptTab({ debugPayloads, metadata }) {
  const [openBlock, setOpenBlock] = useState(null)

  const safetyFlags = (debugPayloads.raw_input_safety_flags || debugPayloads.raw_output_safety_flags)
    ? {
        input: debugPayloads.raw_input_safety_flags || null,
        output: debugPayloads.raw_output_safety_flags || null,
      }
    : null
  const structuredCandidates = debugPayloads.output_safety_structured_output_candidates
    ? {
        selected_payload_index: debugPayloads.output_safety_structured_output_selected_index,
        selection_policy: debugPayloads.output_safety_structured_output_selection_policy,
        extraction_mode: debugPayloads.output_safety_structured_output_extraction_mode,
        candidates: debugPayloads.output_safety_structured_output_candidates,
        raw_output: debugPayloads.output_safety_raw_output,
      }
    : null

  const blocks = [
    { id: 'system', label: 'System prompt', content: debugPayloads.system_prompt },
    { id: 'user',   label: 'User prompt',   content: debugPayloads.raw_prompt },
    { id: 'reasoning', label: 'Reasoning / Rewrite Summary', content: debugPayloads.visible_reasoning_steps },
    { id: 'safety', label: 'Safety Flags', content: safetyFlags },
    { id: 'output', label: 'Raw output',    content: debugPayloads.raw_output },
    { id: 'rewrite', label: 'Query rewrite', content: debugPayloads.rewrite_response },
    { id: 'structured', label: 'Structured Output Candidates', content: structuredCandidates },
  ].filter((b) => b.content)

  if (!blocks.length) {
    return <Empty label="No prompt data available" />
  }

  return (
    <div className="space-y-2">
      {blocks.map((block) => {
        const isOpen = openBlock === block.id
        return (
          <div key={block.id} className="rounded-lg border border-border overflow-hidden">
            <button
              type="button"
              onClick={() => setOpenBlock(isOpen ? null : block.id)}
              className="flex w-full items-center justify-between px-3 py-2.5 text-left hover:bg-bg-tertiary transition-colors"
            >
              <span className="text-[13px] font-medium text-text-secondary">{block.label}</span>
              {isOpen ? <ChevronUp size={12} className="text-text-muted" /> : <ChevronDown size={12} className="text-text-muted" />}
            </button>
            <AnimatePresence initial={false}>
              {isOpen ? (
                <motion.div
                  key="body"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <pre className="max-h-56 overflow-auto border-t border-border bg-bg-tertiary p-3 text-xs leading-relaxed text-text-muted whitespace-pre-wrap break-words">
                    {typeof block.content === 'string' ? block.content : JSON.stringify(block.content, null, 2)}
                  </pre>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        )
      })}
    </div>
  )
}

export default PromptTab
