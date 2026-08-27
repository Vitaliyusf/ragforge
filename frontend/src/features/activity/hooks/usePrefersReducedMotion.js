'use client'

/**
 * Whether the viewer asked for less motion.
 *
 * The stylesheet honours the same query, but the indicator also has to stop
 * *rendering* the moving parts: a rail whose animation was neutralised by
 * CSS is still a bar the user never asked for.
 */
import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const query = window.matchMedia(QUERY)
    setReduced(Boolean(query.matches))
    const onChange = (event) => setReduced(Boolean(event.matches))
    query.addEventListener?.('change', onChange)
    return () => query.removeEventListener?.('change', onChange)
  }, [])

  return reduced
}

export default usePrefersReducedMotion
