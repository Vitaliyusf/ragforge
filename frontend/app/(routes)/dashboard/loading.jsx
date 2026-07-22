/** Dashboard loading state */
export default function Loading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary text-text-primary">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        <div className="text-lg text-accent font-medium">Loading dashboard...</div>
      </div>
    </div>
  )
}
