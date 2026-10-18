import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { getDashboard } from "../lib/api"
import type { DashboardRow } from "../lib/api"
import { fmtDate, humanStatus, plural } from "../lib/format"

/**
 * Port of templates/dashboard.html: one panel per project with the
 * same title-case status, progress line, and counts small-print.
 */
export default function DashboardPage() {
  const [rows, setRows] = useState<DashboardRow[] | null>(null)

  useEffect(() => {
    getDashboard()
      .then((data) => setRows(data.rows))
      .catch(() => setRows([]))
  }, [])

  if (rows === null) return null

  return (
    <>
      <div className="page-heading">
        <div>
          <Link to="/projects">← Projects</Link>
          <span className="eyebrow">Cross-project view</span>
          <h1>Dashboard</h1>
          <p>Every project at a glance.</p>
        </div>
      </div>

      {rows.length > 0 ? (
        <div className="cards" aria-label="Projects">
          {rows.map((row) => (
            <section className="panel" key={row.project.id}>
              <h2>
                <Link to={`/projects/${row.project.id}`}>{row.project.name}</Link>
              </h2>

              <p>
                <strong>{humanStatus(row.status)}</strong>
              </p>

              <p>{row.progress}</p>

              <small>
                {plural(row.open_risks, "open risk")}
                {" · "}
                {plural(row.open_blockers, "open blocker")}
                {" · "}
                {plural(row.open_actions, "open action")}
                {" · "}
                {plural(row.meeting_count, "meeting")}
                {row.last_meeting ? <>{" · last "}{fmtDate(row.last_meeting)}</> : null}
              </small>
            </section>
          ))}
        </div>
      ) : (
        <p>No projects yet.</p>
      )}
    </>
  )
}
