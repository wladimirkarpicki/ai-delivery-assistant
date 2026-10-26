import { useEffect, useRef, useState } from "react"
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom"
import { getProjects } from "../lib/api"
import type { ProjectSummary } from "../lib/api"
import type { Flash } from "../lib/format"
import { useAuth } from "../lib/useAuth"

/**
 * The base.html shell, ported one-to-one: the same native <dialog>
 * command palette fed by the project list, the same theme toggle
 * logic, the same footer. The header keeps one hierarchy: a left nav
 * group (brand, Projects, Dashboard, admin-only Users) of quiet
 * links with the current route marked aria-current, and the working
 * controls on the right - Find, the theme toggle, and the account
 * chip with the sign-out button.
 */
export default function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [paletteProjects, setPaletteProjects] = useState<ProjectSummary[] | null>(null)
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark")

  function handleSignOut() {
    signOut()
    navigate("/login")
  }

  // The flash messages Flask rendered at the top of <main class="container">:
  // pages pass them along when they navigate after an action.
  const flashes: Flash[] =
    (location.state as { flashes?: Flash[] } | null)?.flashes ?? []

  // Ported from base.html: Ctrl+K / Cmd+K opens the command palette.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        openPalette()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  function openPalette() {
    const dialog = dialogRef.current
    if (!dialog) return
    dialog.showModal()
    // The Flask context processor fed the palette with the project
    // list on every request; the SPA fetches it when the palette opens.
    getProjects()
      .then((data) => setPaletteProjects(data.projects))
      .catch(() => setPaletteProjects([]))
  }

  // Ported from base.html: clicking the backdrop (the dialog itself)
  // closes the palette.
  function onDialogClick(event: React.MouseEvent<HTMLDialogElement>) {
    if (event.target === dialogRef.current) dialogRef.current?.close()
  }

  // Ported from base.html: toggle persists the choice; system changes
  // are followed only while no choice is stored.
  function setTheme(nextDark: boolean, persist: boolean) {
    document.documentElement.dataset.theme = nextDark ? "dark" : "light"
    if (persist) {
      try {
        localStorage.setItem("theme", nextDark ? "dark" : "light")
      } catch {
        // Ignore storage failures, as base.html did.
      }
    }
    setDark(nextDark)
  }

  useEffect(() => {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)")
    const storedTheme = () => {
      try {
        return localStorage.getItem("theme")
      } catch {
        return null
      }
    }
    const listener = (event: MediaQueryListEvent) => {
      if (!storedTheme()) setTheme(event.matches, false)
    }
    systemDark.addEventListener("change", listener)
    return () => systemDark.removeEventListener("change", listener)
  }, [])

  const themeLabel = dark ? "Switch to light theme" : "Switch to dark theme"

  // Only the exact "/"-routes light up as the current page; deeper
  // paths (a project, a meeting) mark nothing, like a tab bar.
  const isCurrent = (path: string) => location.pathname === path

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <nav className="app-header__nav" aria-label="Primary">
            <Link className="brand" to="/projects">
              AI Delivery Assistant
            </Link>
            <Link
              className="nav-link"
              to="/projects"
              aria-current={isCurrent("/projects") ? "page" : undefined}
            >
              Projects
            </Link>
            <Link
              className="nav-link"
              to="/dashboard"
              aria-current={isCurrent("/dashboard") ? "page" : undefined}
            >
              Dashboard
            </Link>
            {user?.role === "admin" && (
              <Link
                className="nav-link"
                to="/users"
                aria-current={isCurrent("/users") ? "page" : undefined}
              >
                Users
              </Link>
            )}
          </nav>

          <button
            className="command-trigger"
            type="button"
            onClick={openPalette}
            aria-haspopup="dialog"
            aria-controls="command-palette"
          >
            Find <kbd>Ctrl K</kbd>
          </button>
          <button
            className="icon-button"
            type="button"
            onClick={() => setTheme(!dark, true)}
            aria-label={themeLabel}
            title={themeLabel}
          >
            {dark ? (
              <svg
                width="1.25rem"
                height="1.25rem"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2" />
                <path d="M12 20v2" />
                <path d="m4.93 4.93 1.41 1.41" />
                <path d="m17.66 17.66 1.41 1.41" />
                <path d="M2 12h2" />
                <path d="M20 12h2" />
                <path d="m6.34 17.66-1.41 1.41" />
                <path d="m19.07 4.93-1.41 1.41" />
              </svg>
            ) : (
              <svg
                width="1.25rem"
                height="1.25rem"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
              </svg>
            )}
          </button>

          <div className="app-header__account">
            <span className="user-chip" title="Signed in">
              <span className="user-chip__name">{user?.username}</span>
              <span className={`badge badge--${user?.role ?? "user"}`}>
                {user?.role}
              </span>
            </span>

            <button type="button" className="button--ghost" onClick={handleSignOut}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="container">
        {flashes.map((flash, index) => (
          <div key={index} className={`notice ${flash.category}`}>
            {flash.message}
          </div>
        ))}

        <Outlet />
      </main>

      <footer className="app-footer">
        <div>AI Delivery Assistant</div>
        <div>Auditable delivery memory from every meeting.</div>
      </footer>

      <dialog
        className="command-palette"
        id="command-palette"
        aria-label="Projects"
        ref={dialogRef}
        onClick={onDialogClick}
      >
        {paletteProjects !== null && paletteProjects.length > 0
          ? paletteProjects.map((project) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                onClick={() => dialogRef.current?.close()}
              >
                {project.name}
              </Link>
            ))
          : paletteProjects !== null
            ? <Link to="/projects" onClick={() => dialogRef.current?.close()}>
                Create your first project
              </Link>
            : null}
      </dialog>
    </>
  )
}
