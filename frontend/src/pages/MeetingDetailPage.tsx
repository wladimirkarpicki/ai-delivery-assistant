import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { getMeeting } from "../lib/api"
import type { MeetingDetail } from "../lib/api"
import type { MeetingAnalysis } from "../lib/api"
import { fmtDateTime, humanStatus } from "../lib/format"
import { NotFoundBody } from "./NotFound"

/**
 * Port of templates/meeting_detail.html: original input, the AI
 * analysis status card and finding panels, and the changes timeline.
 */
export default function MeetingDetailPage() {
  const { meetingId } = useParams()
  const [data, setData] = useState<MeetingDetail | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    getMeeting(Number(meetingId))
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 404) {
          setNotFound(true)
        }
      })
  }, [meetingId])

  if (notFound) return <NotFoundBody />

  if (!data) return null

  const meeting = data.meeting
  const analysis: MeetingAnalysis =
    meeting.analysis_json && typeof meeting.analysis_json === "object"
      ? (meeting.analysis_json as MeetingAnalysis)
      : {}
  const hasAnalysis = Object.keys(analysis).length > 0

  const completed = analysis.completed_items ?? []
  const inProgress = analysis.in_progress_items ?? []
  const risks = analysis.risks ?? []
  const blockers = analysis.blockers ?? []
  const actions = analysis.action_items ?? []
  const decisions = analysis.decisions ?? []

  return (
    <article className="record-page">
      <Link to={`/projects/${meeting.project_id}`}>← {meeting.project_name}</Link>
      <span className="eyebrow">Meeting record</span>
      <h1>{meeting.title}</h1>

      <p className="record-meta">
        {fmtDateTime(meeting.created_at)}
        {" · "}
        {meeting.model}
        {meeting.source_filename ? <>{" · "}{meeting.source_filename}</> : null}
      </p>

      <section className="workspace-section">
        <h2>Original input</h2>
        <pre>{meeting.original_text}</pre>
      </section>

      <section className="workspace-section">
        <h2>AI analysis</h2>

        {hasAnalysis ? (
          <>
            <section className="status-card">
              <strong>{humanStatus(analysis.project_status || "unknown")}</strong>
              <p>{analysis.executive_summary || "No executive summary."}</p>
            </section>

            {analysis.progress_summary ? <p>{analysis.progress_summary}</p> : null}

            {(completed.length > 0 || inProgress.length > 0) && (
              <div className="cards" aria-label="Milestones">
                <section className="panel">
                  <h2>Completed</h2>
                  {completed.length > 0 ? (
                    completed.map((item) => (
                      <article key={item}><strong>{item}</strong></article>
                    ))
                  ) : (
                    <p>None.</p>
                  )}
                </section>

                <section className="panel">
                  <h2>In progress</h2>
                  {inProgress.length > 0 ? (
                    inProgress.map((item) => (
                      <article key={item}><strong>{item}</strong></article>
                    ))
                  ) : (
                    <p>None.</p>
                  )}
                </section>
              </div>
            )}

            {(risks.length > 0 || blockers.length > 0 || actions.length > 0 || decisions.length > 0) && (
              <div className="cards" aria-label="Extracted findings">
                <section className="panel">
                  <h2>Risks</h2>
                  {risks.length > 0 ? (
                    risks.map((item, index) => (
                      <article key={index}>
                        <strong>{item.title || "Untitled"}</strong>
                        {item.description ? <p>{item.description}</p> : null}
                        <small>
                          {"Status: "}
                          {item.status || "unspecified"}
                          {item.impact ? <>{" · Impact: "}{item.impact}</> : null}
                          {item.mitigation ? <>{" · Mitigation: "}{item.mitigation}</> : null}
                        </small>
                      </article>
                    ))
                  ) : (
                    <p>None.</p>
                  )}
                </section>

                <section className="panel">
                  <h2>Blockers</h2>
                  {blockers.length > 0 ? (
                    blockers.map((item, index) => (
                      <article key={index}>
                        <strong>{item.title || "Untitled"}</strong>
                        {item.description ? <p>{item.description}</p> : null}
                        <small>
                          {"Status: "}
                          {item.status || "unspecified"}
                        </small>
                      </article>
                    ))
                  ) : (
                    <p>None.</p>
                  )}
                </section>

                <section className="panel">
                  <h2>Action items</h2>
                  {actions.length > 0 ? (
                    actions.map((item, index) => (
                      <article key={index}>
                        <strong>{item.title || "Untitled"}</strong>
                        {item.details ? <p>{item.details}</p> : null}
                        <small>
                          {"Status: "}
                          {item.status || "unspecified"}
                          {item.owner ? <>{" · Owner: "}{item.owner}</> : null}
                          {item.due_date ? <>{" · Due: "}{item.due_date}</> : null}
                        </small>
                      </article>
                    ))
                  ) : (
                    <p>None.</p>
                  )}
                </section>

                <section className="panel">
                  <h2>Decisions</h2>
                  {decisions.length > 0 ? (
                    decisions.map((item, index) => (
                      <article key={index}>
                        <strong>{item.title || "Untitled"}</strong>
                        {item.details ? <p>{item.details}</p> : null}
                      </article>
                    ))
                  ) : (
                    <p>None.</p>
                  )}
                </section>
              </div>
            )}
          </>
        ) : (
          <p>No structured analysis stored for this meeting.</p>
        )}
      </section>

      <section className="workspace-section">
        <h2>Changes from this meeting</h2>

        <ul className="timeline">
          {data.events.length > 0 ? (
            data.events.map((event) => (
              <li key={event.id}>
                <strong>{event.summary}</strong>
              </li>
            ))
          ) : (
            <p>No changes extracted.</p>
          )}
        </ul>
      </section>
    </article>
  )
}
