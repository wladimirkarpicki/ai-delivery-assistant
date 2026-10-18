import { useEffect, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { getHistory } from "../lib/api"
import type { HistoryEvent, HistoryPage as HistoryPageData } from "../lib/api"
import { fmtDateTime, titleKeepUnderscores } from "../lib/format"
import { NotFoundBody } from "./NotFound"

/**
 * Port of templates/history.html: the filter subnav with counts, and
 * the timeline with the history-diff small print. The filter lives in
 * the ?type= query string, exactly like the Flask request arg.
 */
export default function HistoryPage() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const selectedType = searchParams.get("type") ?? ""
  const [data, setData] = useState<HistoryPageData | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    getHistory(Number(projectId), selectedType || undefined)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 404) {
          setNotFound(true)
        }
      })
  }, [projectId, selectedType])

  if (notFound) return <NotFoundBody />

  if (!data) return null

  const totalCount = Object.values(data.type_counts).reduce((sum, n) => sum + n, 0)
  const eventTypes = Object.keys(data.type_counts).sort()

  return (
    <article className="record-page">
      <Link to={`/projects/${data.project.id}`}>← {data.project.name}</Link>
      <span className="eyebrow">Evidence trail</span>
      <h1>Project history</h1>

      <nav className="subnav" aria-label="History filters">
        <Link
          to={`/projects/${data.project.id}/history`}
          aria-current={!selectedType ? "page" : undefined}
        >
          All ({totalCount})
        </Link>

        {eventTypes.map((eventType) => (
          <Link
            key={eventType}
            to={`/projects/${data.project.id}/history?type=${encodeURIComponent(eventType)}`}
            aria-current={selectedType === eventType ? "page" : undefined}
          >
            {titleKeepUnderscores(eventType)} ({data.type_counts[eventType]})
          </Link>
        ))}
      </nav>

      <section className="panel">
        <ul className="timeline">
          {data.events.length > 0 ? (
            data.events.map((event) => <TimelineItem key={event.id} event={event} />)
          ) : (
            <p>No history yet.</p>
          )}
        </ul>
      </section>
    </article>
  )
}

function TimelineItem({ event }: { event: HistoryEvent }) {
  const displayValue = (value: unknown) =>
    value === null || value === undefined ? "(empty)" : String(value)

  return (
    <li>
      <strong>
        {titleKeepUnderscores(event.event_type)}
        {" "}
        {event.entity_type.replace(/_/g, " ")}
      </strong>

      <p>{event.summary}</p>

      {event.changes.length > 0 && (
        <ul className="history-diff">
          {event.changes.map((change, index) => (
            <li key={index}>
              <small>
                {change.field.replace(/_/g, " ")}
                {": "}
                {displayValue(change.old)}
                {" → "}
                {displayValue(change.new)}
              </small>
            </li>
          ))}
        </ul>
      )}

      <small>
        <Link to={`/meetings/${event.meeting_id}`}>
          Meeting #{event.meeting_id}
        </Link>
        {" · "}
        {fmtDateTime(event.created_at)}
      </small>
    </li>
  )
}
