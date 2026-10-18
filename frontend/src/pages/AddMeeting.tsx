import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { getHealth, addMeeting, type HealthInfo } from "@/lib/api"

export function AddMeetingPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const navigate = useNavigate()

  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [title, setTitle] = useState("")
  const [notes, setNotes] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((e: any) => setHealth({ analysis_ready: false, model: null, error: e.message }))
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const result = await addMeeting(projectId, {
        title,
        meeting_notes: notes,
        file,
      })
      navigate(`/meetings/${result.meeting_id}`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <header className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Add meeting</h1>
        <Link to={`/projects/${projectId}/meetings`} className="button button-quiet">
          Back to meetings
        </Link>
      </header>

      {health && !health.analysis_ready && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>
            Analysis is not available: {health.error ?? "unknown error"}
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Paste notes or upload a file (.txt, .md, .docx, .pdf)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="title">Meeting title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Sprint 14 planning"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="notes">Meeting notes</Label>
              <Textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={12}
                placeholder="Paste the raw meeting transcript or notes…"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="file">…or upload a document</Label>
              <Input
                id="file"
                type="file"
                accept=".txt,.md,.docx,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file && (
                <p className="text-xs text-muted-foreground">
                  Selected: {file.name} ({Math.round(file.size / 1024)} KB)
                </p>
              )}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center gap-2">
              <Button
                type="submit"
                disabled={submitting || !health?.analysis_ready || (!notes.trim() && !file)}
              >
                {submitting ? "Analyzing…" : "Analyze meeting"}
              </Button>
              <span className="text-xs text-muted-foreground">
                {health?.model ? `Model: ${health.model}` : "Checking model availability…"}
              </span>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
