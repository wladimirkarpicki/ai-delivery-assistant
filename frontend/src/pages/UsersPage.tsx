import { useEffect, useState } from "react"
import {
  createUser,
  deleteUser,
  getUsers,
  resetUserPassword,
  updateUser,
  type UserRow,
} from "../lib/api"

/**
 * Admin-only account management, in the app's plain panel language:
 * the account list reads like the project list, the add form sits in
 * its own section. The server owns the guardrails (unique usernames,
 * no self-delete, last-admin protection); its messages surface as
 * notices verbatim.
 */
export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [resetting, setResetting] = useState<UserRow | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getUsers()
      .then(setUsers)
      .catch((e: unknown) => {
        setUsers([])
        setError(e instanceof Error ? e.message : "Could not load users.")
      })
  }, [])

  async function run(action: () => Promise<unknown>, message: string): Promise<boolean> {
    setError(null)
    setSuccess(null)
    setBusy(true)

    try {
      await action()
      setSuccess(message)
      setUsers(await getUsers())
      return true
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed.")
      return false
    } finally {
      setBusy(false)
    }
  }

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const formEl = event.currentTarget
    const form = new FormData(formEl)

    const created = await run(
      () =>
        createUser({
          username: String(form.get("username") ?? ""),
          password: String(form.get("password") ?? ""),
          role: (String(form.get("role") ?? "user") as "user" | "admin"),
        }),
      "User added.",
    )

    if (created) formEl.reset()
  }

  async function handleReset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!resetting) return

    const form = new FormData(event.currentTarget)

    await run(
      () => resetUserPassword(resetting.id, String(form.get("password") ?? "")),
      `Password reset for ${resetting.username}.`,
    )
    setResetting(null)
  }

  function toggleRole(user: UserRow) {
    return run(
      () => updateUser(user.id, { role: user.role === "admin" ? "user" : "admin" }),
      `Role updated for ${user.username}.`,
    )
  }

  function removeUser(user: UserRow) {
    return run(() => deleteUser(user.id), `Deleted ${user.username}.`)
  }

  return (
    <>
      {(error || success) && (
        <div className={`notice ${error ? "error" : "success"}`}>
          {error ?? success}
        </div>
      )}

      <div className="page-heading">
        <div>
          <span className="eyebrow">Administration</span>
          <h1>Users</h1>
          <p>Manage who can access the system and what they can do.</p>
        </div>
      </div>

      <section className="workspace-section">
        <h2>Add user</h2>

        <form onSubmit={handleCreate}>
          <label>
            Username
            <input name="username" maxLength={80} required autoComplete="off" />
          </label>

          <label>
            Password (at least 8 characters)
            <input
              type="password"
              name="password"
              minLength={8}
              required
              autoComplete="new-password"
            />
          </label>

          <label>
            Role
            <select name="role" defaultValue="user">
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </label>

          <button type="submit" disabled={busy}>
            Add user
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>Accounts</h2>

        {!users ? null : users.length === 0 ? (
          <p>No users yet.</p>
        ) : (
          <ul className="user-list">
            {users.map((user) => (
              <li key={user.id}>
                <div className="user-row">
                  <div>
                    <strong>{user.username}</strong>
                    {user.is_you && <span className="tag-you">You</span>}
                  </div>
                  <span className={`badge badge--${user.role}`}>{user.role}</span>
                  <div className="user-actions">
                    <button
                      type="button"
                      onClick={() => void toggleRole(user)}
                      disabled={busy}
                    >
                      {user.role === "admin" ? "Make user" : "Make admin"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setError(null)
                        setSuccess(null)
                        setResetting(user)
                      }}
                      disabled={busy}
                    >
                      Reset password…
                    </button>
                    <button
                      type="button"
                      onClick={() => void removeUser(user)}
                      disabled={busy || user.is_you}
                      title={
                        user.is_you ? "You cannot delete yourself." : undefined
                      }
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {resetting?.id === user.id && (
                  <form className="reset-form" onSubmit={handleReset}>
                    <label>
                      New password for {user.username} (at least 8 characters)
                      <input
                        type="password"
                        name="password"
                        minLength={8}
                        required
                        autoComplete="new-password"
                        autoFocus
                      />
                    </label>
                    <div className="user-actions">
                      <button type="submit" disabled={busy}>
                        Set password
                      </button>
                      <button
                        type="button"
                        onClick={() => setResetting(null)}
                        disabled={busy}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
