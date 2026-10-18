import { NotFoundBody } from "./NotFound"

/** Route-level 404 page (Flask errorhandler 404 -> templates/404.html). */
export default function NotFoundPage() {
  return <NotFoundBody />
}
