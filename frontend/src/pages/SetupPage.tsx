import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { authSetup, ApiError } from "../lib/api"
import { useAuth } from "../lib/useAuth"

/**
 * First-run setup: creates the initial admin while the installation
 * has no users. Once bootstrap is complete the server refuses with
 * "Setup is already completed." and this page sends the visitor to
 * the sign-in page instead.
 */
export default function SetupPage() {
  const { adoptSession } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
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
      const data = await authSetup(
        String(form.get("username") ?? ""),
        password,
      )
      adoptSession(data)
      navigate("/projects")
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 400) {
        // Bootstrap is already done: the login page is the only way in.
        navigate("/login")
        return
      }
      setError(e instanceof Error ? e.message : "Setup failed.")
      setBusy(false)
    }
  }

  return (
    <main className="container auth-page">
      <section className="auth-card panel">
        <span className="eyebrow">AI Delivery Assistant</span>
        <h1>First-time setup</h1>
        <p>
          Create the initial admin account. This page is only available
          while the installation has no users.
        </p>

        {error && <div className="notice error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <label>
            Username
            <input
              name="username"
              autoComplete="username"
              maxLength={80}
              required
              autoFocus
            />
          </label>

          <label>
            Password (at least 8 characters)
            <input
              type="password"
              name="password"
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>

          <label>
            Confirm password
            <input
              type="password"
              name="confirm"
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>

          <button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create admin account"}
          </button>
        </form>
      </section>
    </main>
  )
}
