import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        // Tags in the legacy material: a small clear pane of glass
        // with a hairline; solid ink only for the loudest states.
        default:
          "rounded-[var(--radius-input)] bg-[color-mix(in_oklch,var(--primary)_86%,transparent)] text-[var(--primary-foreground)] [a&]:hover:bg-primary/90",
        secondary:
          "rounded-[var(--radius-input)] bg-[var(--glass-control)] text-[var(--foreground)] [box-shadow:inset_0_1px_0_var(--glass-control-rim),0_0_0_1px_var(--glass-edge)]",
        destructive:
          "rounded-[var(--radius-input)] bg-[var(--destructive)] text-white [a&]:hover:bg-destructive/90",
        outline:
          "rounded-[var(--radius-input)] text-[var(--muted-foreground)] [box-shadow:0_0_0_1px_var(--glass-edge)] [a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        ghost: "[a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        link: "text-primary underline-offset-4 [a&]:hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
