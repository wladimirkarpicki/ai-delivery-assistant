import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { RefreshCw } from "lucide-react"
import { getProjects } from "@/lib/api"
import type { ProjectSummary } from "@/lib/api"

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const data = await getProjects()
      setProjects(data.projects)
      setError(null)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="container">
      <header className="page-heading">
        <div>
          <h1>Projects</h1>
          <p>Meeting notes become project memory: status, risks, blockers, actions, decisions.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="icon-button"
            onClick={load}
            disabled={loading}
            aria-label="Refresh projects"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <Link to="/projects/new" className="button">
            New project
          </Link>
        </div>
      </header>

      {loading && <p className="mt-6 text-center text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="notice error mt-6">{error}</p>}

      {!loading && !error && (
        <ul className="project-list mt-8">
          {projects.map((p) => (
            <li key={p.id}>
              <Link to={`/projects/${p.id}/overview`}>{p.name}</Link>
              {p.description && <span className="text-sm text-muted-foreground">{p.description}</span>}
              <small>
                Last updated:{" "}
                {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : "Never"}
              </small>
            </li>
          ))}

          {projects.length === 0 && (
            <li className="border-0">
              <p className="text-muted-foreground mb-4">No projects yet.</p>
              <Link to="/projects/new" className="button">
                Create your first project
              </Link>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
