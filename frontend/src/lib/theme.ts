import { useCallback, useEffect, useState } from "react"

const KEY = "ada-theme"

export function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const stored = localStorage.getItem(KEY)
    if (stored === "light" || stored === "dark") return stored
    return "dark" // dark is the material as designed
  })

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
    localStorage.setItem(KEY, theme)
  }, [theme])

  const toggle = useCallback(() => setTheme(t => t === "dark" ? "light" : "dark"), [])
  return { theme, toggle }
}
