import { useCallback, useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  getReviewQueue,
  resolveReview,
  type ReviewQueueItem,
  type ProjectSummary,
} from "@/lib/api"

function QueueCard({
  projectId,
  item,
  onResolved,
}: {
  projectId: number
  item: ReviewQueueItem
  onResolved: () => void
}) {
  const [targetId, setTargetId] = useState("")
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const title = String(item.new_item?.title ?? item.event.summary)
  const details = String(item.new_item?.details ?? item.new_item?.description ?? "")

  async function act(action: "create" | "link" | "dismiss") {
    setError(null)
    if (action === "link" && !targetId) {
      setError("Pick an item to link to first.")
      return
    }
    setBusy(true)
    try {
      await resolveReview(projectId, item.event.id, {
        action,
        target_item_id: action === "link" ? Number(targetId) : null,
        note,
      })
      onResolved()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">{title}</CardTitle>
          <Badge variant="secondary">{item.event.entity_type.replace("_", " ")}</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-3">
        {details && <p className="text-sm text-muted-foreground whitespace-pre-wrap">{details}</p>}

        <div className="space-y-1.5">
          <Label>Link to existing item (for “Link”)</Label>
          <select
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            <option value="">— pick an item —</option>
            {item.targets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <Label>Note (optional)</Label>
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this decision…" />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button size="sm" disabled={busy} onClick={() => act("create")}>
            Create new
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => act("link")}>
            Link
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => act("dismiss")}>
            Dismiss
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export function ReviewQueuePage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [queue, setQueue] = useState<ReviewQueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    getReviewQueue(projectId)
      .then((data) => {
        setProject(data.project)
        setQueue(data.queue)
        setError(null)
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <div className="p-6 text-center">Loading…</div>
  if (error) return <div className="p-6 text-center text-destructive">{error}</div>

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">{project?.name}: review queue</h1>
          <p className="text-sm text-muted-foreground">{queue.length} item(s) need review</p>
        </div>
        <Link to={`/projects/${projectId}/overview`} className="button button-quiet">
          Overview
        </Link>
      </header>

      {queue.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            Nothing to review — consolidation had no open questions.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {queue.map((item) => (
            <QueueCard key={item.event.id} projectId={projectId} item={item} onResolved={load} />
          ))}
        </div>
      )}
    </div>
  )
}
