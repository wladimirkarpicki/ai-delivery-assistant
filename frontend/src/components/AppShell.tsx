import { useEffect, useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { BarChart3, Folder, History as HistoryIcon, Moon, Search, Sun } from "lucide-react"
import { cn } from "@/lib/utils"
import { useTheme } from "@/lib/theme"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Dialog, DialogContent } from "@/components/ui/dialog"

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/projects", label: "Projects", icon: Folder },
]

const paletteItems = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/projects", label: "Projects", icon: Folder },
  { href: "/projects", label: "Project history", icon: HistoryIcon },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { theme, toggle } = useTheme()

  // Ctrl+K / Cmd+K opens the command palette.
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
    <div className="flex flex-col h-screen w-full">
      <header className="flex items-center justify-between h-14 border-b bg-background px-4">
        <div className="flex items-center gap-2">
          <Link to="/" className="flex items-center gap-2">
            <Folder className="h-5 w-5 text-primary" />
            <span className="font-bold">AI Delivery Assistant</span>
          </Link>
        </div>

        <nav className="flex items-center gap-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              to={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground",
                location.pathname.startsWith(item.href) && "bg-accent text-accent-foreground",
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-2 text-muted-foreground"
            onClick={() => setPaletteOpen(true)}
          >
            <Search className="h-4 w-4" />
            <span className="hidden sm:inline">Search…</span>
            <kbd className="pointer-events-none hidden sm:inline rounded border bg-muted px-1.5 font-mono text-[10px]">
              Ctrl K
            </kbd>
          </Button>
          <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </header>

      <main className="flex-1 overflow-auto">{children}</main>

      {/* Command palette (Ctrl+K) */}
      <Dialog open={paletteOpen} onOpenChange={setPaletteOpen}>
        <DialogContent className="p-0 max-w-md">
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
