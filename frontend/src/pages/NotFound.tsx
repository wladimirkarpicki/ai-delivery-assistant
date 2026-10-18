import { Link } from "react-router-dom"

/** The body of templates/404.html, reused wherever a record is missing. */
export function NotFoundBody() {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Error 404</span>
          <h1>Page not found</h1>
          <p>The page you are looking for does not exist or was moved.</p>
        </div>
      </div>

      <section className="panel">
        <p>
          <Link className="button" to="/projects">Back to projects</Link>
        </p>
      </section>
    </>
  )
}
