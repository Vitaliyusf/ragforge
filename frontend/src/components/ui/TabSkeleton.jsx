'use client'

function SkeletonLine({ className = '', delay = 0 }) {
  return (
    <div
      className={`animate-shimmer rounded-lg ${className}`}
      style={{ animationDelay: `${delay}ms` }}
    />
  )
}

export default function TabSkeleton() {
  return (
    <div className="flex min-h-0 flex-1 gap-4 overflow-hidden p-3 md:p-4">
      <aside
        className="hidden w-[276px] shrink-0 flex-col overflow-hidden rounded-2xl border p-3 xl:flex"
        style={{ background: 'var(--glass)', borderColor: 'var(--border)' }}
      >
        <SkeletonLine className="mb-3 h-8 w-full" />
        <SkeletonLine className="mb-5 h-9 w-full" delay={70} />
        <SkeletonLine className="mb-3 h-3 w-20" delay={110} />
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((index) => (
            <SkeletonLine key={index} className="h-12 w-full" delay={140 + index * 60} />
          ))}
        </div>
        <SkeletonLine className="mt-auto h-20 w-full" delay={420} />
      </aside>

      <div
        className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-3xl border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)', boxShadow: 'var(--shadow-md)' }}
      >
        <div className="flex h-[58px] shrink-0 items-center gap-3 border-b px-4" style={{ borderColor: 'var(--border)' }}>
          <SkeletonLine className="h-9 w-9" />
          <div className="space-y-1.5">
            <SkeletonLine className="h-3 w-32" delay={60} />
            <SkeletonLine className="h-2.5 w-48" delay={100} />
          </div>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center px-6">
          <SkeletonLine className="mb-5 h-16 w-16 rounded-2xl" />
          <SkeletonLine className="mb-3 h-7 w-72 max-w-full" delay={100} />
          <SkeletonLine className="mb-8 h-4 w-96 max-w-full" delay={150} />
          <div className="grid w-full max-w-3xl grid-cols-1 gap-2 sm:grid-cols-2">
            {[0, 1, 2, 3].map((index) => (
              <SkeletonLine key={index} className="h-14 w-full" delay={180 + index * 65} />
            ))}
          </div>
        </div>

        <div className="px-4 pb-4">
          <SkeletonLine className="mx-auto h-[84px] max-w-3xl rounded-2xl" delay={430} />
        </div>
      </div>
    </div>
  )
}
