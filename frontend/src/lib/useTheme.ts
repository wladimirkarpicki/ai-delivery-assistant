import { useEffect, useState } from "react"

/**
 * The current data-theme of <html>, kept live: AppShell's toggle (and
 * the pre-paint script in index.html) write
 * documentElement.dataset.theme, so a MutationObserver on that one
 * attribute is the single source of truth for every themed consumer.
 */

export type Theme = "light" | "dark"

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light"
}

export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(currentTheme)

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(currentTheme()))
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    })
    return () => observer.disconnect()
  }, [])

  return theme
}
