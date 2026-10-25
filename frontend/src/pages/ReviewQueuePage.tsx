import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { getReviewQueue, resolveReview } from "../lib/api"
import type { ReviewQueueItem } from "../lib/api"
import { fmtDateTime } from "../lib/format"
import { NotFoundBody } from "./NotFound"

/**
 * Port of templates/review_queue.html: one panel per pending finding
 * with the same three explicit resolutions (create / link / dismiss).
 * Errors surface as the same notices the Flask flashes produced.
 */
export default function ReviewQueuePage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<{ project: { id: number; name: string }; queue: ReviewQueueItem[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)

  const load = useCallback(() => {
    getReviewQueue(Number(projectId))
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 404) {
          setNotFound(true)
        } else if (e instanceof Error) {
          setError(e.message)
        }
      })
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  async function resolve(eventId: number, body: { action: string; target_item_id?: number | null; note?: string }) {
    setError(null)
    try {
      await resolveReview(Number(projectId), eventId, body)
      // Flask: flash("Review item resolved.", "success") + redirect.
      navigate(".", {
        replace: true,
        state: { flashes: [{ category: "success", message: "Review item resolved." }] },
      })
      load()
    } catch (e: unknown) {
      // Flask: flash(message, "error") + redirect back to the queue.
      const message = e instanceof Error ? e.message : String(e)
      navigate(".", {
        replace: true,
        state: { flashes: [{ category: "error", message }] },
      })
      load()
    }
  }

  if (notFound) return <NotFoundBody />

  if (!data) return null

  return (
    <article className="record-page">
      <div className="page-heading">
        <div>
          <Link to={`/projects/${data.project.id}`}>← {data.project.name}</Link>
          <span className="eyebrow">Quality gate</span>
          <h1>Review queue</h1>
          <p>
            Findings the consolidation guardrails could not apply safely.
            Resolve each one explicitly: nothing is silently dropped.
          </p>
        </div>
      </div>

      {error && <div className="notice error">{error}</div>}

      {data.queue.length > 0 ? (
        data.queue.map((entry) => <ReviewEntry key={entry.event.id} entry={entry} onResolve={resolve} />)
      ) : (
        <section className="panel">
          <p>Nothing needs review.</p>
        </section>
      )}
    </article>
  )
}

function ReviewEntry({
  entry,
  onResolve,
}: {
  entry: ReviewQueueItem
  onResolve: (eventId: number, body: { action: string; target_item_id?: number | null; note?: string }) => Promise<void>
}) {
  const newTitle = typeof entry.new_item.title === "string" ? entry.new_item.title : ""
  const newStatus = typeof entry.new_item.status === "string" ? entry.new_item.status : ""
  const firstTargetId = entry.targets.length > 0 ? entry.targets[0].id : undefined

  return (
    <section className="panel">
      <p><strong>{entry.event.summary}</strong></p>

      {newTitle ? (
        <p>
          {"Finding: "}
          <strong>{newTitle}</strong>
          {newStatus ? <>{" · status: "}{newStatus}</> : null}
        </p>
      ) : null}

      <small>
        Meeting #{entry.event.meeting_id}
        {" · "}
        {fmtDateTime(entry.event.created_at)}
      </small>

      <form onSubmit={(e) => { e.preventDefault(); void onResolve(entry.event.id, { action: "create" }) }}>
        <button type="submit">Create item</button>
      </form>

      {entry.targets.length > 0 && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            const form = new FormData(e.currentTarget)
            const raw = String(form.get("target_item_id") ?? "")
            void onResolve(entry.event.id, {
              action: "link",
              target_item_id: raw ? Number(raw) : null,
            })
          }}
        >
          <label>
            Link to existing:
            <select name="target_item_id" defaultValue={firstTargetId}>
              {entry.targets.map((target) => (
                <option key={target.id} value={target.id}>
                  #{target.id} — {target.title}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Link</button>
        </form>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault()
          const form = new FormData(e.currentTarget)
          void onResolve(entry.event.id, {
            action: "dismiss",
            note: String(form.get("note") ?? ""),
          })
        }}
      >
        <label>
          <input type="text" name="note" placeholder="Optional note" />
        </label>
        <button type="submit">Dismiss</button>
      </form>
    </section>
  )
}
