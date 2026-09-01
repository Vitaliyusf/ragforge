'use client'

import { Lock } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { useI18n } from '@/i18n'
import { CATEGORY_CONFIG } from './memoryConfig'

function CategoryBadge({ category }) {
  const { t } = useI18n()
  const cfg = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.chat_insight
  const isReadOnly = category === 'user_insight'
  return (
    <div className="flex items-center gap-1">
      {isReadOnly && <Lock size={10} style={{ color: 'var(--fg-soft)' }} />}
      <Badge
        size="xs"
        style={{ background: cfg.bg, color: cfg.color, borderColor: 'transparent' }}
      >
        {t(cfg.labelKey)}
      </Badge>
    </div>
  )
}

export default CategoryBadge
