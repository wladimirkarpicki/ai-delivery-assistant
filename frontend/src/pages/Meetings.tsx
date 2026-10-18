import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { getMeetings, type MeetingSummary, type ProjectSummary } from "@/lib/api"

export function MeetingsPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    getMeetings(projectId)
      .then((data) => {
        setProject(data.project)
        setMeetings(data.meetings)
        setError(null)
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  if (loading) return <div className="p-6 text-center">Loading…</div>
  if (error) return <div className="p-6 text-center text-destructive">{error}</div>

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">{project?.name}: meetings</h1>
          <p className="text-sm text-muted-foreground">{meetings.length} meeting(s) analyzed</p>
        </div>
        <div className="flex gap-2">
          <Link to={`/projects/${projectId}/overview`} className="button button-quiet">
            Overview
          </Link>
          <Link to={`/projects/${projectId}/meetings/add`} className="button">
            Add meeting
          </Link>
        </div>
      </header>

      {meetings.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            No meetings yet. Add the first one to build project memory.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {meetings.map((m) => (
            <Card key={m.id}>
              <CardHeader className="py-3">
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="text-base">
                    <Link to={`/meetings/${m.id}`} className="hover:underline">
                      {m.title}
                    </Link>
                  </CardTitle>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {m.created_at ? new Date(m.created_at).toLocaleString() : ""}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="py-2 flex items-center gap-2 text-xs text-muted-foreground">
                {m.source_filename && <Badge variant="outline">{m.source_filename}</Badge>}
                <span>{m.provider} / {m.model}</span>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
