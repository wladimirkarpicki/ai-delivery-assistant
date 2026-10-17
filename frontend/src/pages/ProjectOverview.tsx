import { useCallback, useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import type { ReactNode } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  getProjectOverview,
  manualResolve,
  type ProjectOverview as Overview,
  type Risk,
  type Blocker,
  type ActionItem,
} from "@/lib/api"

type ItemAction = "resolve" | "reopen"

function ItemRow({
  title,
  description,
  meta,
  action,
  onAction,
}: {
  title: string
  description?: string
  meta?: string
  action: ItemAction
  onAction: () => void
}) {
  return (
    <li className="flex items-start justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        {description && (
          <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">{description}</p>
        )}
        {meta && <p className="text-xs text-muted-foreground mt-0.5">{meta}</p>}
      </div>
      <Button variant="outline" size="sm" onClick={onAction} className="shrink-0">
        {action === "resolve" ? "Resolve" : "Reopen"}
      </Button>
    </li>
  )
}

function ItemPanel<T>({
  heading,
  items,
  emptyText,
  renderItem,
}: {
  heading: string
  items: T[]
  emptyText: string
  renderItem: (item: T) => ReactNode
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">
          {heading}
          <Badge variant="secondary" className="ml-2">
            {items.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {items.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2">{emptyText}</p>
        ) : (
          <ul className="divide-y">{items.map(renderItem)}</ul>
        )}
      </CardContent>
    </Card>
  )
}

export function ProjectOverviewPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [data, setData] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    getProjectOverview(projectId)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  async function handleManual(
    itemType: "risk" | "blocker" | "action_item",
    itemId: number,
    action: ItemAction,
  ) {
    try {
      await manualResolve(projectId, itemType, itemId, action)
      load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  if (loading && !data) return <div className="p-6 text-center">Loading…</div>
  if (error && !data) return <div className="p-6 text-center text-destructive">{error}</div>
  if (!data) return <div className="p-6 text-center">Not found.</div>

  const { project, state } = data

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <header className="flex items-start justify-between gap-4 flex-wrap mb-2">
        <div>
          <h1 className="text-2xl font-bold">{project.name}</h1>
          {project.description && (
            <p className="text-sm text-muted-foreground mt-0.5">{project.description}</p>
          )}
        </div>
        <nav className="flex gap-2 flex-wrap">
          <Button asChild variant="outline" size="sm">
            <Link to={`/projects/${projectId}/meetings`}>Meetings ({data.meeting_count})</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to={`/projects/${projectId}/history`}>History</Link>
          </Button>
          <Button asChild variant={data.needs_review_count > 0 ? "default" : "outline"} size="sm">
            <Link to={`/projects/${projectId}/review`}>
              Review{data.needs_review_count > 0 ? ` (${data.needs_review_count})` : ""}
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to={`/projects/${projectId}/report`}>Report</Link>
          </Button>
        </nav>
      </header>

      <Card className="mb-4">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <CardTitle className="text-sm font-semibold">Delivery status</CardTitle>
            <Badge variant={state.delivery_status === "on_track" ? "default" : "secondary"}>
              {state.delivery_status.replace("_", " ")}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm">{state.progress_summary}</p>
          {state.completed_items.length > 0 && (
            <>
              <Separator className="my-3" />
              <p className="text-xs font-medium text-muted-foreground mb-1">Completed</p>
              <ul className="list-disc pl-5 text-sm space-y-0.5">
                {state.completed_items.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </>
          )}
          {state.in_progress_items.length > 0 && (
            <>
              <Separator className="my-3" />
              <p className="text-xs font-medium text-muted-foreground mb-1">In progress</p>
              <ul className="list-disc pl-5 text-sm space-y-0.5">
                {state.in_progress_items.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <ItemPanel
          heading="Risks"
          items={data.risks}
          emptyText="No open risks."
          renderItem={(r: Risk) => (
            <ItemRow
              key={`risk-${r.id}`}
              title={r.title}
              description={r.description}
              meta={r.impact ? `Impact: ${r.impact}` : undefined}
              action="resolve"
              onAction={() => handleManual("risk", r.id, "resolve")}
            />
          )}
        />
        <ItemPanel
          heading="Resolved risks"
          items={data.resolved_risks}
          emptyText="Nothing resolved yet."
          renderItem={(r: Risk) => (
            <ItemRow
              key={`rrisk-${r.id}`}
              title={r.title}
              meta={r.resolved_at ? `Resolved ${new Date(r.resolved_at).toLocaleDateString()}` : undefined}
              action="reopen"
              onAction={() => handleManual("risk", r.id, "reopen")}
            />
          )}
        />
        <ItemPanel
          heading="Blockers"
          items={data.blockers}
          emptyText="No open blockers."
          renderItem={(b: Blocker) => (
            <ItemRow
              key={`blocker-${b.id}`}
              title={b.title}
              description={b.description}
              action="resolve"
              onAction={() => handleManual("blocker", b.id, "resolve")}
            />
          )}
        />
        <ItemPanel
          heading="Resolved blockers"
          items={data.resolved_blockers}
          emptyText="Nothing resolved yet."
          renderItem={(b: Blocker) => (
            <ItemRow
              key={`rblocker-${b.id}`}
              title={b.title}
              meta={b.resolved_at ? `Resolved ${new Date(b.resolved_at).toLocaleDateString()}` : undefined}
              action="reopen"
              onAction={() => handleManual("blocker", b.id, "reopen")}
            />
          )}
        />
        <ItemPanel
          heading="Action items"
          items={data.actions}
          emptyText="No open actions."
          renderItem={(a: ActionItem) => (
            <ItemRow
              key={`action-${a.id}`}
              title={a.title}
              description={a.details}
              meta={
                [a.owner ? `Owner: ${a.owner}` : null, a.due_date ? `Due: ${a.due_date}` : null]
                  .filter(Boolean)
                  .join(" · ") || undefined
              }
              action="resolve"
              onAction={() => handleManual("action_item", a.id, "resolve")}
            />
          )}
        />
        <ItemPanel
          heading="Completed actions"
          items={data.completed_actions}
          emptyText="Nothing completed yet."
          renderItem={(a: ActionItem) => (
            <ItemRow
              key={`caction-${a.id}`}
              title={a.title}
              meta={a.completed_at ? `Completed ${new Date(a.completed_at).toLocaleDateString()}` : undefined}
              action="reopen"
              onAction={() => handleManual("action_item", a.id, "reopen")}
            />
          )}
        />
      </div>

      {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      {loading && data && <p className="mt-4 text-xs text-muted-foreground">Refreshing…</p>}
    </div>
  )
}
