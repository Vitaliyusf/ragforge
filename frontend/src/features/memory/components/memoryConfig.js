/**
 * Category styling and options for long-term memory entries.
 *
 * The `value` keys are the backend's category enum and never change with
 * the interface language; only `labelKey` is what the reader sees.
 */

export const MAX_CHARS = 120

export const CATEGORY_CONFIG = {
  user_preference: { labelKey: 'memory.categoryPreference', color: 'var(--info)',    bg: 'var(--info-soft)',    variant: 'info'    },
  user_background: { labelKey: 'memory.categoryBackground', color: 'var(--accent)',  bg: 'var(--accent-soft)',  variant: 'accent'  },
  chat_insight:    { labelKey: 'memory.categoryInsight',    color: 'var(--success)', bg: 'var(--success-soft)', variant: 'success' },
  user_insight:    { labelKey: 'memory.categoryInsight',    color: 'var(--fg-soft)', bg: 'var(--surface-hover)',variant: 'default' },
}

export const CATEGORY_OPTIONS = [
  { value: 'user_preference', labelKey: 'memory.optionUserPreference' },
  { value: 'user_background', labelKey: 'memory.optionUserBackground' },
  { value: 'chat_insight',    labelKey: 'memory.optionChatInsight'    },
]
