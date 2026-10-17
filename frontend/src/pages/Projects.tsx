import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
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
    <div className="p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Projects</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </header>

      {loading && <div className="mt-6 text-center py-8">Loading…</div>}
      {error && (
        <div className="mt-6 text-center py-8 text-destructive">{error}</div>
      )}

      {!loading && !error && (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map(p => (
            <Card key={p.id}>
              <CardHeader>
                <CardTitle>
                  <Link
                    to={`/projects/${p.id}/overview`}
                    className="hover:underline"
                  >
                    {p.name}
                  </Link>
                </CardTitle>
                {p.description && (
                  <CardDescription>{p.description}</CardDescription>
                )}
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Last updated:{" "}
                  {p.updated_at
                    ? new Date(p.updated_at).toLocaleDateString()
                    : "Never"}
                </p>
              </CardContent>
            </Card>
          ))}

          {projects.length === 0 && (
            <div className="col-span-full text-center py-12">
              <p className="text-muted-foreground mb-4">No projects yet.</p>
              <Button asChild>
                <Link to="/projects/new">Create your first project</Link>
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
