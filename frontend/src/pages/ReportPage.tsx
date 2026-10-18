import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { getReport, reportDownloadUrl } from "../lib/api"
import { NotFoundBody } from "./NotFound"

/**
 * Port of templates/report.html: the heading with the download
 * button (a plain attachment link, as before) and the report <pre>.
 */
export default function ReportPage() {
  const { projectId } = useParams()
  const [data, setData] = useState<{ project: { id: number; name: string }; report: string } | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    getReport(Number(projectId))
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 404) {
          setNotFound(true)
        }
      })
  }, [projectId])

  if (notFound) return <NotFoundBody />

  if (!data) return null

  return (
    <>
      <div className="page-heading">
        <div>
          <Link to={`/projects/${data.project.id}`}>← {data.project.name}</Link>
          <span className="eyebrow">Status report</span>
          <h1>Status report</h1>
        </div>

        <a className="button" href={reportDownloadUrl(data.project.id)} download>
          Download .md
        </a>
      </div>

      <article className="record-page">
        <section className="workspace-section">
          <pre>{data.report}</pre>
        </section>
      </article>
    </>
  )
}
