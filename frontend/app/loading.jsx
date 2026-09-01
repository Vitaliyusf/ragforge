/** Global loading state */
import { cookies } from 'next/headers'
import { LOCALE_COOKIE, normalizeLocale } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

export default async function Loading() {
  const cookieStore = await cookies()
  const locale = normalizeLocale(cookieStore.get(LOCALE_COOKIE)?.value)

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary">
      <div className="flex flex-col items-center gap-6">
        <div className="relative">
          <div className="w-14 h-14 rounded-2xl bg-primary-soft animate-pulse" />
          <div className="absolute inset-0 w-14 h-14 rounded-2xl border-2 border-accent border-t-transparent animate-spin" />
        </div>
        <p className="text-text-muted font-medium">{translate(locale, 'common.loading')}</p>
      </div>
    </div>
  )
}
