import { useEffect, useRef, useState } from "react"
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom"
import { getProjects } from "../lib/api"
import type { ProjectSummary } from "../lib/api"
import type { Flash } from "../lib/format"
import { useAuth } from "../lib/useAuth"

/**
 * The base.html shell, ported one-to-one: the same header markup, the
 * same native <dialog> command palette fed by the project list, the
 * same theme toggle logic, the same footer. Authentication adds the
 * account chip on the right: username, role, the admin-only Users
 * link, and the sign-out button.
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

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <Link className="brand" to="/projects">
            AI Delivery Assistant
          </Link>
          <Link className="button" to="/dashboard">
            Dashboard
          </Link>
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
            {dark ? "☀" : "☾"}
          </button>

          <div className="app-header__account">
            {user?.role === "admin" && (
              <Link className="button" to="/users">
                Users
              </Link>
            )}

            <span className="user-chip" title="Signed in">
              <span className="user-chip__name">{user?.username}</span>
              <span className={`badge badge--${user?.role ?? "user"}`}>
                {user?.role}
              </span>
            </span>

            <button type="button" onClick={handleSignOut}>
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
