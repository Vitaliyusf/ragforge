/** 404 page */
import Link from 'next/link'
import { Compass } from 'lucide-react'
import Button from '@/components/ui/Button'

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg-primary text-text-primary p-8">
      <div className="flex flex-col items-center max-w-md text-center">
        <div className="w-24 h-24 rounded-2xl bg-accent/10 flex items-center justify-center mb-6">
          <Compass className="text-accent" size={48} />
        </div>
        <h2 className="text-6xl font-bold text-accent mb-2">404</h2>
        <h3 className="text-xl font-semibold text-text-primary mb-2">Lost in the void</h3>
        <p className="text-text-secondary mb-8">
          This page could not be found. Maybe it drifted off into another dimension.
        </p>
        <Link href="/">
          <Button variant="primary" size="lg">
            Back to home
          </Button>
        </Link>
      </div>
    </div>
  )
}
