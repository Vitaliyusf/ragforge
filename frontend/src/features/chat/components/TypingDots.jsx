'use client'

/** Three resting dots shown before the first token of an answer arrives. */
export default function TypingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      {[0, 0.2, 0.4].map((delay, index) => (
        <span
          key={index}
          className="h-2 w-2 rounded-full bg-text-muted motion-safe:animate-pulse"
          style={{ animationDelay: `${delay}s` }}
        />
      ))}
    </div>
  )
}
