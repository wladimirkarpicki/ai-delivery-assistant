import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../lib/useAuth"

/**
 * The sign-in page. Validation errors surface as the same notice the
 * rest of the app uses; on success the app lands on the projects
 * page, exactly where the pre-auth redirect chain ended up.
 */
export default function LoginPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setBusy(true)

    const form = new FormData(event.currentTarget)

    try {
      await signIn(
        String(form.get("username") ?? ""),
        String(form.get("password") ?? ""),
      )
      navigate("/projects")
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sign-in failed.")
      setBusy(false)
    }
  }

  return (
    <main className="container auth-page">
      <section className="auth-card panel">
        <span className="eyebrow">AI Delivery Assistant</span>
        <h1>Sign in</h1>
        <p>Enter your credentials to continue.</p>

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
            Password
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
            />
          </label>

          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  )
}
