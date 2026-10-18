import { useEffect, useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { BarChart3, Folder } from "lucide-react"
import { useTheme } from "@/lib/theme"
import {
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  Command,
} from "@/components/ui/command"
import { Dialog, DialogContent } from "@/components/ui/dialog"

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/projects", label: "Projects" },
]

const paletteItems = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/projects", label: "Projects", icon: Folder },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { theme, toggle } = useTheme()

  // Ctrl+K / Cmd+K toggles the command palette.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setPaletteOpen((open) => !open)
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [])

  function go(href: string) {
    setPaletteOpen(false)
    navigate(href)
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="app-header">
        <div className="app-header__inner">
          <Link to="/" className="brand">
            AI Delivery Assistant
          </Link>

          <nav className="topnav flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                to={item.href}
                aria-current={
                  location.pathname.startsWith(item.href) ? "page" : undefined
                }
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <button
            type="button"
            className="command-trigger flex items-center gap-2"
            onClick={() => setPaletteOpen(true)}
          >
            Search…
            <kbd>Ctrl K</kbd>
          </button>

          <button
            type="button"
            className="icon-button"
            onClick={toggle}
            aria-label="Toggle theme"
            title={theme === "dark" ? "Switch to light" : "Switch to dark"}
          >
            {theme === "dark" ? "☾" : "☀"}
          </button>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="app-footer">
        <span>AI Delivery Assistant</span>
        <span>FastAPI + React</span>
      </footer>

      {/* Command palette (Ctrl+K) */}
      <Dialog open={paletteOpen} onOpenChange={setPaletteOpen}>
        <DialogContent className="pane-popover p-0 max-w-md">
          <Command>
            <CommandInput placeholder="Go to…" />
            <CommandList>
              <CommandEmpty>No results.</CommandEmpty>
              <CommandGroup>
                {paletteItems.map((item) => (
                  <CommandItem key={item.label} onSelect={() => go(item.href)}>
                    <item.icon className="mr-2 h-4 w-4" />
                    {item.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </DialogContent>
      </Dialog>
    </div>
  )
}
