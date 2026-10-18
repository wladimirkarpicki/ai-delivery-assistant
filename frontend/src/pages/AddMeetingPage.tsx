import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { addMeeting, getHealth } from "../lib/api"

/**
 * Port of templates/add_meeting.html. The health check gates the
 * submit button exactly as the Flask view did; validation errors
 * render in the same inline notice spot; a successful analysis
 * redirects to the meeting record carrying the same flash messages
 * (consolidation warning first, then the success notice).
 */
export default function AddMeetingPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [analysisReady, setAnalysisReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    // The model list is only a health check so the form can fail fast.
    getHealth()
      .then((health) => {
        setAnalysisReady(health.analysis_ready)
        if (health.error) setError(health.error)
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
      })
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    const form = new FormData(event.currentTarget)
    const title = String(form.get("title") ?? "")
    const meetingNotes = String(form.get("meeting_notes") ?? "")
    const fileInput = form.get("meeting_file")
    const file =
      fileInput instanceof File && fileInput.name ? fileInput : null

    try {
      const result = await addMeeting(Number(projectId), {
        title,
        meeting_notes: meetingNotes,
        file,
      })

      const flashes: { category: "warning" | "success"; message: string }[] = []

      if (result.warning) {
        flashes.push({ category: "warning", message: result.warning })
      }
      flashes.push({
        category: "success",
        message: "Meeting saved and project memory updated.",
      })

      navigate(`/meetings/${result.meeting_id}`, { state: { flashes } })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <Link to={`/projects/${projectId}`}>← Project</Link>
          <span className="eyebrow">New evidence</span>
          <h1>Add meeting</h1>
          <p>Upload or paste the source record. Analysis stays attached to this project.</p>
        </div>
      </div>

      {error && <div className="notice error">{error}</div>}

      <form onSubmit={handleSubmit}>
        <label>
          Meeting title
          <input name="title" maxLength={250} placeholder="Weekly delivery meeting" />
        </label>

        <label>
          Upload notes
          <span>PDF, DOCX, TXT, or Markdown (max 20 MB)</span>
          <input type="file" name="meeting_file" accept=".pdf,.docx,.txt,.md" />
        </label>

        <p className="hint">
          Or paste notes below.
        </p>

        <label>
          Meeting notes
          <textarea name="meeting_notes" rows={14} />
        </label>

        <button type="submit" disabled={!analysisReady || submitting}>
          {submitting ? "Analyzing…" : "Analyze and save"}
        </button>
      </form>
    </>
  )
}
