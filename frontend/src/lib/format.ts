/**
 * Display formatting helpers, ported one-to-one from the Jinja
 * filters the templates used, so every page renders exactly the same
 * strings as the Flask app did.
 */

/** `2026-10-18T03:40:00` -> `2026-10-18 03:40` (Jinja `%Y-%m-%d %H:%M`). */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return ""
  return iso.slice(0, 16).replace("T", " ")
}

/** `2026-10-18T03:40:00` -> `2026-10-18` (Jinja `%Y-%m-%d`). */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return ""
  return iso.slice(0, 10)
}

/** Jinja `replace('_', ' ')|title`: `at_risk` -> `At Risk`. */
export function humanStatus(value: string | null | undefined): string {
  const spaced = (value ?? "").replace(/_/g, " ")
  return spaced.replace(/(^|\s)([a-z])/g, (_, sep, char) => sep + char.toUpperCase())
}

/** Jinja `event_type|title`: `manual_resolve` -> `Manual_Resolve`. */
export function titleKeepUnderscores(value: string): string {
  return value.replace(/(^|_)([a-z])/g, (_, sep, char) => sep + char.toUpperCase())
}

/** Jinja `{{ n }} {{ noun }}{{ 's' if n != 1 else '' }}`. */
export function plural(n: number, noun: string): string {
  return `${n} ${noun}${n !== 1 ? "s" : ""}`
}

/** A flash message rendered by base.html's notice area. */
export interface Flash {
  category: "message" | "error" | "warning" | "success"
  message: string
}
