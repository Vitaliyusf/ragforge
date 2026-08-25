/** Category styling and options for long-term memory entries. */

export const MAX_CHARS = 120

export const CATEGORY_CONFIG = {
  user_preference: { label: 'Preference', color: 'var(--info)',    bg: 'var(--info-soft)',    variant: 'info'    },
  user_background: { label: 'Background', color: 'var(--accent)',  bg: 'var(--accent-soft)',  variant: 'accent'  },
  chat_insight:    { label: 'Insight',    color: 'var(--success)', bg: 'var(--success-soft)', variant: 'success' },
  user_insight:    { label: 'Insight',    color: 'var(--fg-soft)', bg: 'var(--surface-hover)',variant: 'default' },
}

export const CATEGORY_OPTIONS = [
  { value: 'user_preference', label: 'User Preference' },
  { value: 'user_background', label: 'User Background' },
  { value: 'chat_insight',    label: 'Chat Insight'    },
]
