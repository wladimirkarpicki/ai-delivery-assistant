import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { getReport, reportDownloadUrl, type ProjectSummary } from "@/lib/api"

export function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [report, setReport] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getReport(projectId)
      .then((data) => {
        setProject(data.project)
        setReport(data.report)
        setError(null)
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  if (loading) return <div className="p-6 text-center">Loading…</div>
  if (error) return <div className="p-6 text-center text-destructive">{error}</div>

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">{project?.name}: status report</h1>
          <p className="text-sm text-muted-foreground">Generated from current project memory</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to={`/projects/${projectId}/overview`}>Overview</Link>
          </Button>
          <Button asChild size="sm">
            <a href={reportDownloadUrl(projectId)} download>
              Download .md
            </a>
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Report (markdown)</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <pre className="whitespace-pre-wrap text-sm leading-relaxed font-mono">
            {report}
          </pre>
        </CardContent>
      </Card>
    </div>
  )
}
