import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { createProject, getProjects } from "../lib/api"
import type { ProjectSummary } from "../lib/api"

/**
 * Port of templates/projects.html. The DOM, classes, labels, and flow
 * are unchanged: the "New project" form creates the project and the
 * browser lands on the project overview, exactly as the Flask
 * redirect did. Validation errors surface as the same notice texts.
 */
export default function ProjectsPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getProjects()
      .then((data) => setProjects(data.projects))
      .catch(() => {
        // The projects page has no unknown-record case, but a dead
        // backend must not render a blank page either.
        setProjects([])
        setError("Could not load projects.")
      })
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const form = new FormData(event.currentTarget)
    const name = String(form.get("name") ?? "").trim()
    const description = String(form.get("description") ?? "").trim()

    try {
      const created = await createProject(name, description)
      navigate(`/projects/${created.id}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <>
      {error && <div className="notice error">{error}</div>}

      <div className="page-heading">
        <div>
          <span className="eyebrow">Delivery workspace</span>
          <h1>Projects</h1>
          <p>Choose a project to review what changed, what is at risk, and what needs an owner.</p>
        </div>
      </div>

      <section className="workspace-section">
        <h2>New project</h2>

        <form onSubmit={handleSubmit}>
          <label>
            Name
            <input name="name" required maxLength={200} />
          </label>

          <label>
            Description
            <textarea name="description" rows={3} />
          </label>

          <button>Create project</button>
        </form>
      </section>

      <section className="panel">
        <h2>Your projects</h2>

        {projects && projects.length > 0 ? (
          <ul className="project-list">
            {projects.map((project) => (
              <li key={project.id}>
                <Link to={`/projects/${project.id}`}>{project.name}</Link>
                <span>{project.description || "No description"}</span>
              </li>
            ))}
          </ul>
        ) : projects ? (
          <p>No projects yet. Create one to start storing meetings.</p>
        ) : null}
      </section>
    </>
  )
}
