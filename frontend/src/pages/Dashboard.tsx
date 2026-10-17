import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { getDashboard, type DashboardRow } from "@/lib/api"

const statusVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  on_track: "default",
  at_risk: "secondary",
  off_track: "destructive",
  unknown: "outline",
}

export function DashboardPage() {
  const [rows, setRows] = useState<DashboardRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getDashboard()
      .then((data) => {
        setRows(data.rows)
        setError(null)
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-center">Loading…</div>
  if (error) return <div className="p-6 text-center text-destructive">{error}</div>

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Cross-project dashboard</h1>

      {rows.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            No projects yet — create one on the Projects page.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((row) => (
            <Card key={row.project.id}>
              <CardContent className="py-4">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <Link
                      to={`/projects/${row.project.id}/overview`}
                      className="font-semibold hover:underline"
                    >
                      {row.project.name}
                    </Link>
                    <p className="text-sm text-muted-foreground mt-0.5">{row.progress}</p>
                  </div>
                  <Badge variant={statusVariant[row.status] ?? "outline"}>
                    {row.status}
                  </Badge>
                </div>

                <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
                  <span>Risks open: <strong className="text-foreground">{row.open_risks}</strong></span>
                  <span>Blockers open: <strong className="text-foreground">{row.open_blockers}</strong></span>
                  <span>Actions open: <strong className="text-foreground">{row.open_actions}</strong></span>
                  <span>Meetings: <strong className="text-foreground">{row.meeting_count}</strong></span>
                  {row.last_meeting && (
                    <span>Last: {new Date(row.last_meeting).toLocaleDateString()}</span>
                  )}
                  <Link
                    to={`/projects/${row.project.id}/report`}
                    className="ml-auto hover:underline text-foreground"
                  >
                    Report →
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
