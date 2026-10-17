import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import type { ReactNode } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { getMeeting, type MeetingDetail, type HistoryEvent } from "@/lib/api"

const sectionLabels: Record<string, string> = {
  executive_summary: "Executive summary",
  project_status: "Project status",
  progress_summary: "Progress summary",
  completed_items: "Completed items",
  in_progress_items: "In progress items",
  risks: "Risks",
  blockers: "Blockers",
  action_items: "Action items",
  decisions: "Decisions",
}

export function MeetingDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<MeetingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState("executive_summary")

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getMeeting(Number(id))
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="p-6 text-center">Loading…</div>
  if (error) return <div className="p-6 text-center text-destructive">{error}</div>
  if (!data) return <div className="p-6 text-center">Not found.</div>

  const analysis = data.meeting?.analysis_json || {}

  function renderSection(key: string): ReactNode {
    const items = analysis[key]
    if (items === undefined) return <p className="text-muted-foreground mb-1">—</p>
    if (Array.isArray(items))
      return (
        <ul className="list-disc pl-5 space-y-1 text-sm">
          {items.map((s: string, i: number) => (
            <li key={i}>{String(s)}</li>
          ))}
        </ul>
      )
    return <p className="text-sm">{String(items)}</p>
  }

  function renderFindingList(section: "risks" | "blockers" | "action_items" | "decisions") {
    const items = (analysis as any)[section] || []
    if (!Array.isArray(items) || items.length === 0)
      return <p className="text-muted-foreground text-sm mb-2">—</p>
    return (
      <ul className="space-y-3">
        {items.map((f: any, i: number) => (
          <li key={i}>
            <div className="font-medium text-sm">{f.title}</div>
            {f.details && (
              <div className="text-sm text-muted-foreground mt-0.5">{f.details}</div>
            )}
            {f.status && (
              <Badge variant={f.status === "open" ? "default" : "secondary"} className="mt-1">
                {f.status}
              </Badge>
            )}
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <nav className="flex flex-wrap gap-1 mb-4">
        {Object.entries(sectionLabels).map(([k, label]) => (
          <Button
            key={k}
            variant={active === k ? "default" : "ghost"}
            size="sm"
            onClick={() => setActive(k)}
          >
            {label}
          </Button>
        ))}
      </nav>

      <Card>
        <CardHeader>
          <CardTitle>Meeting #{data.meeting.id}</CardTitle>
          <div className="text-sm text-muted-foreground space-x-3 mt-2">
            <span>Project: {data.meeting.project_id}</span>
            <span>Source: {data.meeting.source_filename ?? "paste"}</span>
            <span>Provider: {data.meeting.provider}</span>
            <span>Model: {data.meeting.model}</span>
            <span>Created: {data.meeting.created_at}</span>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <Separator className="my-3" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-y-6 gap-x-8">
            {Object.entries(sectionLabels).map(([k, label]) => (
              <div key={k}>
                <h3 className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                  {label}
                </h3>
                {renderSection(k)}
              </div>
            ))}
            <div>
              <h3 className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                Findings
              </h3>
              {renderFindingList("risks")}
              {renderFindingList("blockers")}
              {renderFindingList("action_items")}
              {renderFindingList("decisions")}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Original meeting notes</CardTitle>
        </CardHeader>
        <CardContent className="whitespace-pre-wrap leading-relaxed text-sm">
          {data.meeting.original_text}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Analysis notes</CardTitle>
        </CardHeader>
        <CardContent className="whitespace-pre-wrap leading-relaxed text-sm">
          {data.meeting.analysis_text}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Change history</CardTitle>
        </CardHeader>
        <CardContent>
          {data.events.length === 0 ? (
            <p className="text-muted-foreground text-sm">No events recorded.</p>
          ) : (
            <ul className="divide-y">
              {data.events.map((e: HistoryEvent) => (
                <li key={e.id} className="py-2 flex justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <span className="font-medium text-sm capitalize">{e.event_type}</span>
                    <span className="text-xs text-muted-foreground ml-2">{e.summary}</span>
                    {e.changes && e.changes.length > 0 && (
                      <span className="text-xs text-muted-foreground ml-2">
                        {e.changes
                          .map((c: any) => `${c.field}: ${c.old}→${c.new}`)
                          .join(", ")}
                      </span>
                    )}
                    {e.created_at && (
                      <span className="text-xs text-muted-foreground ml-2">{e.created_at}</span>
                    )}
                  </div>
                  <Badge variant="outline">{e.entity_type}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="mt-4">
        <Button asChild variant="outline" size="sm">
          <Link to="../">Back</Link>
        </Button>
      </div>
    </div>
  )
}
