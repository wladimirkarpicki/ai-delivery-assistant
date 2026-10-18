import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { getProjectOverview, manualResolve } from "../lib/api"
import type { ProjectOverview } from "../lib/api"
import { fmtDate, humanStatus } from "../lib/format"
import { NotFoundBody } from "./NotFound"

/**
 * Port of templates/project_overview.html: the same status card, the
 * same six panels, and the same inline resolve/reopen forms. Each
 * form posts to the JSON endpoint and then shows the exact flash
 * message the Flask redirect produced, in the same top-of-page spot.
 */
export default function ProjectOverviewPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<ProjectOverview | null>(null)
  const [notFound, setNotFound] = useState(false)

  const load = useCallback(() => {
    const id = Number(projectId)
    getProjectOverview(id)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 404) {
          setNotFound(true)
        }
      })
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  async function resolve(itemType: "risk" | "blocker" | "action_item", itemId: number, action: "resolve" | "reopen") {
    const id = Number(projectId)
    const result = await manualResolve(id, itemType, itemId, action)
    // The Flask view redirected back to the overview with a flash;
    // the SPA re-renders the same notice at the top of the page.
    navigate(".", {
      replace: true,
      state: { flashes: [{ category: result.level === "warning" ? "warning" : "success", message: result.message }] },
    })
    load()
  }

  if (notFound) return <NotFoundBody />

  if (!data) return null

  const state = data.state

  return (
    <>
      <div className="page-heading">
        <div>
          <Link to="/projects">← Projects</Link>
          <span className="eyebrow">Project workbench</span>
          <h1>{data.project.name}</h1>
          <p>{data.project.description}</p>
        </div>

        <Link className="button" to={`/projects/${data.project.id}/meetings/new`}>
          Add meeting
        </Link>
      </div>

      <nav className="subnav">
        <Link to={`/projects/${data.project.id}/meetings`}>
          Meetings ({data.meeting_count})
        </Link>
        <Link to={`/projects/${data.project.id}/history`}>
          History
        </Link>
        <Link to={`/projects/${data.project.id}/report`}>
          Report
        </Link>
        <Link to={`/projects/${data.project.id}/review`}>
          Review{data.needs_review_count > 0 ? ` (${data.needs_review_count})` : ""}
        </Link>
      </nav>

      <section className="status-card">
        <strong>{humanStatus(state.delivery_status)}</strong>
        <p>{state.progress_summary}</p>
      </section>

      <div className="cards" aria-label="Delivery work">
        <section className="panel">
          <h2>Open risks</h2>

          {data.risks.length > 0 ? (
            data.risks.map((item) => (
              <article key={item.id}>
                <strong>{item.title}</strong>
                <p>{item.description}</p>
                <small>
                  {"Impact: "}
                  {item.impact}
                  {item.mitigation ? <>{" · Mitigation: "}{item.mitigation}</> : null}
                </small>
                <form
                  className="inline-form"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void resolve("risk", item.id, "resolve")
                  }}
                >
                  <button type="submit" name="action" value="resolve">Resolve</button>
                </form>
              </article>
            ))
          ) : (
            <p>None.</p>
          )}
        </section>

        <section className="panel">
          <h2>Resolved risks</h2>

          {data.resolved_risks.length > 0 ? (
            data.resolved_risks.map((item) => (
              <article key={item.id}>
                <strong>{item.title}</strong>
                <small>{"Resolved "}{item.resolved_at ? fmtDate(item.resolved_at) : ""}</small>
                <form
                  className="inline-form"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void resolve("risk", item.id, "reopen")
                  }}
                >
                  <button type="submit" name="action" value="reopen">Reopen</button>
                </form>
              </article>
            ))
          ) : (
            <p>None.</p>
          )}
        </section>

        <section className="panel">
          <h2>Open blockers</h2>

          {data.blockers.length > 0 ? (
            data.blockers.map((item) => (
              <article key={item.id}>
                <strong>{item.title}</strong>
                <p>{item.description}</p>
                <form
                  className="inline-form"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void resolve("blocker", item.id, "resolve")
                  }}
                >
                  <button type="submit" name="action" value="resolve">Resolve</button>
                </form>
              </article>
            ))
          ) : (
            <p>None.</p>
          )}
        </section>

        <section className="panel">
          <h2>Resolved blockers</h2>

          {data.resolved_blockers.length > 0 ? (
            data.resolved_blockers.map((item) => (
              <article key={item.id}>
                <strong>{item.title}</strong>
                <small>{"Resolved "}{item.resolved_at ? fmtDate(item.resolved_at) : ""}</small>
                <form
                  className="inline-form"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void resolve("blocker", item.id, "reopen")
                  }}
                >
                  <button type="submit" name="action" value="reopen">Reopen</button>
                </form>
              </article>
            ))
          ) : (
            <p>None.</p>
          )}
        </section>

        <section className="panel">
          <h2>Open actions</h2>

          {data.actions.length > 0 ? (
            data.actions.map((item) => (
              <article key={item.id}>
                <strong>{item.title}</strong>
                <p>
                  {item.owner || "Unassigned"}
                  {item.due_date ? <>{" · due "}{item.due_date}</> : null}
                </p>
                <form
                  className="inline-form"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void resolve("action_item", item.id, "resolve")
                  }}
                >
                  <button type="submit" name="action" value="resolve">Complete</button>
                </form>
              </article>
            ))
          ) : (
            <p>None.</p>
          )}
        </section>

        <section className="panel">
          <h2>Completed actions</h2>

          {data.completed_actions.length > 0 ? (
            data.completed_actions.map((item) => (
              <article key={item.id}>
                <strong>{item.title}</strong>
                <small>{"Completed "}{item.completed_at ? fmtDate(item.completed_at) : ""}</small>
                <form
                  className="inline-form"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void resolve("action_item", item.id, "reopen")
                  }}
                >
                  <button type="submit" name="action" value="reopen">Reopen</button>
                </form>
              </article>
            ))
          ) : (
            <p>None.</p>
          )}
        </section>
      </div>
    </>
  )
}
