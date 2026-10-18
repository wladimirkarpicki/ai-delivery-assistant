import { useEffect, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { getHistory, type HistoryEvent, type ProjectSummary } from "@/lib/api"

export function HistoryPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedType = searchParams.get("type") ?? ""

  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [events, setEvents] = useState<HistoryEvent[]>([])
  const [typeCounts, setTypeCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    getHistory(projectId, selectedType || undefined)
      .then((data) => {
        setProject(data.project)
        setEvents(data.events)
        setTypeCounts(data.type_counts)
        setError(null)
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId, selectedType])

  if (loading) return <div className="p-6 text-center">Loading…</div>
  if (error) return <div className="p-6 text-center text-destructive">{error}</div>

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">{project?.name}: history</h1>
          <p className="text-sm text-muted-foreground">{events.length} event(s)</p>
        </div>
        <Link to={`/projects/${projectId}/overview`} className="button button-quiet">
          Overview
        </Link>
      </header>

      <div className="flex flex-wrap gap-2 mb-4">
        <button
          type="button"
          className="subnav-link"
          aria-current={selectedType === "" ? "page" : undefined}
          onClick={() => setSearchParams({})}
        >
          All
        </button>
        {Object.entries(typeCounts).map(([type, count]) => (
          <button
            key={type}
            type="button"
            className="subnav-link"
            aria-current={selectedType === type ? "page" : undefined}
            onClick={() => setSearchParams({ type })}
          >
            {type.replace("_", " ")} ({count})
          </button>
        ))}
      </div>

      {events.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            No history events{selectedType ? ` of type "${selectedType}"` : ""} yet.
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {events.map((event) => (
            <li key={event.id}>
              <Card>
                <CardContent className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm">{event.summary}</p>
                      {event.changes.length > 0 && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {event.changes.map((c) => `${c.field}: ${String(c.old)} → ${String(c.new)}`).join("; ")}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">
                        {event.created_at ? new Date(event.created_at).toLocaleString() : ""}
                        {" · "}
                        <Link to={`/meetings/${event.meeting_id}`} className="hover:underline">
                          meeting #{event.meeting_id}
                        </Link>
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <Badge variant="outline">{event.event_type.replace("_", " ")}</Badge>
                      <span className="text-xs text-muted-foreground">{event.entity_type}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
