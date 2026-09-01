/** 404 page */
import { cookies } from 'next/headers'
import Link from 'next/link'
import { Compass } from 'lucide-react'
import Button from '@/components/ui/Button'
import { LOCALE_COOKIE, normalizeLocale } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

export default async function NotFound() {
  // A server component, so the locale comes from the cookie rather than
  // from context — the same source the root layout stamps `dir` from.
  const cookieStore = await cookies()
  const locale = normalizeLocale(cookieStore.get(LOCALE_COOKIE)?.value)
  const t = (key) => translate(locale, key)

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg-primary text-text-primary p-8">
      <div className="flex flex-col items-center max-w-md text-center">
        <div className="w-24 h-24 rounded-2xl flex items-center justify-center mb-6">
          <Compass className="text-accent" size={48} />
        </div>
        <h2 className="text-6xl font-bold text-accent mb-2">404</h2>
        <h3 className="text-2xl font-semibold text-text-primary mb-2">
          {t('error.notFoundTitle')}
        </h3>
        <p className="text-text-secondary mb-8">{t('error.notFoundDescription')}</p>
        <Link href="/">
          <Button variant="primary" size="lg">
            {t('error.backToHome')}
          </Button>
        </Link>
      </div>
    </div>
  )
}
