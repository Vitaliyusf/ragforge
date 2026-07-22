export function normalizeChatMode(mode) {
  const normalized = String(mode || 'regular').trim().toLowerCase()
  if (normalized === 'quick') return 'regular'
  if (normalized === 'extended') return 'extended'
  return 'regular'
}

export function isExtendedMode(mode) {
  return normalizeChatMode(mode) === 'extended'
}

