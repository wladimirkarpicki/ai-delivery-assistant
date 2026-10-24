import type { Theme } from "./useTheme"

/**
 * Chart colors per theme, mirroring the Solid Glass tokens in
 * static/tokens.css: the material's own hues (brand, link,
 * destructive) lead both categorical palettes, a muted slate closes
 * them for "unknown" and "completed" series, and the axis, grid, and
 * tooltip colors are the theme's border, muted-foreground, popover,
 * and popover-edge tokens.
 */

export interface ChartTheme {
  /** Categorical palette; pick by index, wrap on overflow. */
  categorical: string[]
  /** Axis lines and grid strokes (--border). */
  grid: string
  /** Axis tick text (--muted-foreground). */
  axis: string
  tooltip: {
    /** --popover */
    background: string
    /** --popover-edge */
    border: string
    /** --popover-foreground */
    text: string
  }
  /** Consistent kind colors across the mix donut and stacked bars. */
  kind: {
    risks: string
    blockers: string
    actions: string
  }
  /** Muted series: completed counts, resolved partners. */
  muted: string
}

const LIGHT: ChartTheme = {
  categorical: [
    "oklch(0.55 0.13 166)",
    "oklch(0.5 0.17 255)",
    "oklch(0.577 0.245 27.325)",
    "oklch(0.66 0.15 75)",
    "oklch(0.52 0.18 300)",
    "oklch(0.55 0.12 230)",
    "oklch(0.62 0.15 30)",
    "oklch(0.5 0.05 265)",
  ],
  grid: "oklch(0.3 0.02 265 / 13%)",
  axis: "oklch(0.47 0 0)",
  tooltip: {
    background: "oklch(0.985 0.003 265 / 96%)",
    border: "oklch(0.38 0.03 265 / 22%)",
    text: "oklch(0.16 0 0)",
  },
  kind: {
    risks: "oklch(0.577 0.245 27.325)",
    blockers: "oklch(0.66 0.15 75)",
    actions: "oklch(0.55 0.13 166)",
  },
  muted: "oklch(0.5 0.05 265)",
}

const DARK: ChartTheme = {
  categorical: [
    "oklch(0.78 0.13 166)",
    "oklch(0.76 0.12 250)",
    "oklch(0.704 0.191 22.216)",
    "oklch(0.8 0.14 85)",
    "oklch(0.72 0.17 300)",
    "oklch(0.7 0.11 230)",
    "oklch(0.75 0.13 45)",
    "oklch(0.72 0.02 265)",
  ],
  grid: "oklch(1 0 0 / 11%)",
  axis: "oklch(0.72 0 0)",
  tooltip: {
    background: "oklch(0.22 0 0 / 96%)",
    border: "oklch(1 0 0 / 6%)",
    text: "oklch(0.985 0 0)",
  },
  kind: {
    risks: "oklch(0.704 0.191 22.216)",
    blockers: "oklch(0.8 0.14 85)",
    actions: "oklch(0.78 0.13 166)",
  },
  muted: "oklch(0.72 0.02 265)",
}

export function chartTheme(theme: Theme): ChartTheme {
  return theme === "dark" ? DARK : LIGHT
}
