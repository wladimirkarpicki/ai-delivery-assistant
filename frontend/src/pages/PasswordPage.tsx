import { useState } from "react"
import { Link } from "react-router-dom"
import { changeOwnPassword } from "../lib/api"

/**
 * Self-service password change, available to every signed-in
 * account. The server requires the current password; its refusal
 * ("Current password is incorrect.") surfaces as a notice.
 */
export default function PasswordPage() {
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const form = new FormData(event.currentTarget)
    const password = String(form.get("password") ?? "")
    const confirm = String(form.get("confirm") ?? "")

    if (password !== confirm) {
      setError("Passwords do not match.")
      return
    }

    setBusy(true)

    try {
      await changeOwnPassword(
        String(form.get("current") ?? ""),
        password,
      )
      setDone(true)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Change failed.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Your account</span>
          <h1>Change your password</h1>
          <p>
            Enter your current password, then choose a new one (at least 8
            characters).
          </p>
        </div>
      </div>

      {error && <div className="notice error">{error}</div>}
      {done && (
        <div className="notice success">
          Password changed. <Link to="/projects">Back to projects</Link>
        </div>
      )}

      {!done && (
        <section className="workspace-section">
          <form onSubmit={handleSubmit}>
            <label>
              Current password
              <input
                type="password"
                name="current"
                autoComplete="current-password"
                required
              />
            </label>

            <label>
              New password (at least 8 characters)
              <input
                type="password"
                name="password"
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>

            <label>
              Confirm new password
              <input
                type="password"
                name="confirm"
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>

            <button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Change password"}
            </button>
          </form>
        </section>
      )}
    </>
  )
}
