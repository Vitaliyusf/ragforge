/**
 * useChatInit — initialisation hook for the chat tab.
 *
 * Loads LLM implementations and file-based suggested prompts in a single
 * Promise.all, eliminating two separate sequential useEffect calls and
 * preventing layout jank from waterfall fetches.
 */
'use client'

import { useState, useEffect } from 'react'
import { useSelector } from 'react-redux'
import { modelService } from '@/features/models'
import { fileService } from '@/features/files'

const DEFAULT_SUGGESTED_PROMPTS = [
  'What can you help me with?',
  'Summarize my documents',
  'Explain this concept',
]

/**
 * @returns {{
 *   implementations: Array,
 *   selectedImplementation: string|null,
 *   setSelectedImplementation: Function,
 *   suggestedPrompts: string[],
 * }}
 */
export function useChatInit() {
  const [implementations, setImplementations] = useState([])
  const [selectedImplementation, setSelectedImplementation] = useState(null)
  const [suggestedPrompts, setSuggestedPrompts] = useState(DEFAULT_SUGGESTED_PROMPTS)

  // Re-load suggested prompts whenever the files list changes (via Redux event)
  const filesVersion = useSelector((state) => state.events.filesVersion)

  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        const [implData, questData] = await Promise.all([
          modelService.getImplementations().catch(() => null),
          fileService.getSuggestedQuestions().catch(() => null),
        ])

        if (cancelled) return

        if (implData?.implementations?.length) {
          setImplementations(implData.implementations)
          setSelectedImplementation(
            implData.current ?? implData.implementations[0]?.name ?? null
          )
        }

        const questions = questData?.suggested_questions ?? []
        setSuggestedPrompts(
          questions.length > 0
            ? [...questions, ...DEFAULT_SUGGESTED_PROMPTS].slice(0, 6)
            : DEFAULT_SUGGESTED_PROMPTS
        )
      } catch (err) {
        console.error('[useChatInit] init error:', err)
      }
    }

    init()
    return () => { cancelled = true }
  // filesVersion is intentionally included so prompts refresh on file changes
  }, [filesVersion]) // eslint-disable-line react-hooks/exhaustive-deps

  return { implementations, selectedImplementation, setSelectedImplementation, suggestedPrompts }
}
