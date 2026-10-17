import { cn } from "@/lib/utils"

/**
 * Three dots flashing in sequence. The only thing in the UI that says "still
 * running" — status colour is reserved for runs that have stopped.
 */
export function DotLoader({
  className,
  dotClassName,
}: {
  className?: string
  dotClassName?: string
}) {
  return (
    <span className={cn("flex items-center gap-[2px]", className)}>
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          style={{ animationDelay: index * 160 + "ms" }}
          className={cn(
            "size-[3px] animate-dot-flash rounded-full bg-status-running",
            dotClassName
          )}
        />
      ))}
    </span>
  )
}
