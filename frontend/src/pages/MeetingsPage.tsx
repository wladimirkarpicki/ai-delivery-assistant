import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { getMeetings } from "../lib/api"
import type { MeetingSummary, ProjectSummary } from "../lib/api"
import { fmtDateTime } from "../lib/format"
import { NotFoundBody } from "./NotFound"

/**
 * Port of templates/meetings.html: the meeting list panel with the
 * same date · model line.
 */
export default function MeetingsPage() {
  const { projectId } = useParams()
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [meetings, setMeetings] = useState<MeetingSummary[] | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    getMeetings(Number(projectId))
      .then((data) => {
        setProject(data.project)
        setMeetings(data.meetings)
      })
      .catch((e: unknown) => {
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 404) {
          setNotFound(true)
        }
      })
  }, [projectId])

  if (notFound) return <NotFoundBody />

  if (!project || meetings === null) return null

  return (
    <>
      <div className="page-heading">
        <div>
          <Link to={`/projects/${project.id}`}>← {project.name}</Link>
          <span className="eyebrow">Meeting record</span>
          <h1>Meetings</h1>
        </div>

        <Link className="button" to={`/projects/${project.id}/meetings/new`}>
          Add meeting
        </Link>
      </div>

      <section className="panel">
        <ul className="project-list">
          {meetings.length > 0 ? (
            meetings.map((meeting) => (
              <li key={meeting.id}>
                <Link to={`/meetings/${meeting.id}`}>{meeting.title}</Link>
                <span>
                  {fmtDateTime(meeting.created_at)}
                  {" · "}
                  {meeting.model}
                </span>
              </li>
            ))
          ) : (
            <li>No meetings stored yet.</li>
          )}
        </ul>
      </section>
    </>
  )
}
