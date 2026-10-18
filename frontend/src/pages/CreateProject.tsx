import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { createProject } from "@/lib/api"

export function CreateProjectPage() {
  const navigate = useNavigate()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const created = await createProject(name.trim(), description.trim())
      navigate(`/projects/${created.id}/overview`)
    } catch (e: any) {
      setError(e.message)
      setSubmitting(false)
    }
  }

  return (
    <div className="container record-page">
      <header className="page-heading">
        <div>
          <h1>New project</h1>
          <p>A project owns its meeting memory: risks, blockers, actions, and decisions.</p>
        </div>
        <Link to="/projects" className="button button-quiet">
          Cancel
        </Link>
      </header>

      <form onSubmit={handleSubmit} className="fields mt-8">
        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Atlas migration"
            required
            autoFocus
          />
        </label>
        <label>
          Description (optional)
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this project about?"
          />
        </label>

        {error && <p className="notice error">{error}</p>}

        <div>
          <button type="submit" disabled={submitting || !name.trim()}>
            {submitting ? "Creating…" : "Create project"}
          </button>
        </div>
      </form>
    </div>
  )
}
