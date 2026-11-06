/**
 * Session shape for the API client.
 *
 * There is no token storage here any more. The session lives in an
 * httpOnly cookie issued by /api/auth/login and /api/auth/setup, which
 * JavaScript cannot read, so no client code can either hold or leak it.
 * lib/api.ts sends it with `credentials: "include"`.
 *
 * auth_user is still persisted because the shell needs to render the
 * signed-in identity before any request resolves, and it carries no
 * capability: the role is re-read from the database on every request
 * server-side, so editing this value in devtools grants nothing.
 */

const USER_KEY = "aida_user"

export interface AuthUser {
  id: number
  username: string
  role: "user" | "admin"
}

export function setAuthUser(user: AuthUser): void {
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    // Storage can be unavailable (private mode); the shell then shows
    // defaults until the first request resolves, which is harmless.
  }
}

export function getAuthUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)

    if (!raw) {
      return null
    }

    const parsed: unknown = JSON.parse(raw)

    if (
      parsed &&
      typeof parsed === "object" &&
      typeof (parsed as AuthUser).id === "number" &&
      typeof (parsed as AuthUser).username === "string" &&
      ((parsed as AuthUser).role === "user" ||
        (parsed as AuthUser).role === "admin")
    ) {
      return parsed as AuthUser
    }

    return null
  } catch {
    // Malformed or unreadable storage reads as signed out.
    return null
  }
}

export function removeAuthUser(): void {
  try {
    localStorage.removeItem(USER_KEY)
  } catch {
    // Nothing stored, nothing to drop.
  }
}
