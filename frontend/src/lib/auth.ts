/**
 * Bearer-token storage for the API client.
 *
 * The token lives in localStorage under TOKEN_KEY; every request the
 * client sends carries it as an Authorization header. The API refuses
 * dead tokens with 401, and the client reacts by dropping the token
 * and returning to the sign-in page (see lib/api.ts).
 */

const TOKEN_KEY = "aida_token"

export interface AuthUser {
  id: number
  username: string
  role: "user" | "admin"
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    // Storage can be unavailable (private mode); auth then simply
    // never persists, exactly like being signed out.
    return null
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Ignore storage failures: the session just won't survive a
    // reload.
  }
}

export function removeToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing stored, nothing to drop.
  }
}
