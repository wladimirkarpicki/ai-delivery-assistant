/**
 * Auth context: resolves the live account on mount, signs users in and
 * out.
 *
 * The session itself is an httpOnly cookie, so this state is only a
 * convenience copy of who is signed in: the header badge, the RequireAuth
 * gate, and the admin-only routes read it. The role is re-read from the
 * database on every request server-side, so editing this copy grants
 * nothing.
 *
 * On mount, whether a session exists is decided by the server: a cookie
 * that is absent or dead answers /api/auth/me with 401, which is what
 * makes this a real check rather than a guess from local storage.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"

import { authLogin, getMe, type AuthResponse } from "./api"
import {
  getAuthUser,
  removeAuthUser,
  setAuthUser,
  type AuthUser,
} from "./auth"

interface AuthState {
  user: AuthUser | null
  loading: boolean
  /** Sign in with credentials; throws ApiError on refusal. */
  signIn: (username: string, password: string) => Promise<void>
  /** Adopt a session the setup bootstrap just issued. */
  adoptSession: (data: AuthResponse) => void
  /** Forget the account. The cookie is cleared by signing out below. */
  signOut: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  // Start from the cached identity so the shell does not flash a signed
  // out layout on every reload; the request below corrects it.
  const [user, setUser] = useState<AuthUser | null>(() => getAuthUser())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    getMe()
      .then((account) => {
        if (cancelled) {
          return
        }
        setUser(account)
        setAuthUser(account)
      })
      .catch(() => {
        if (cancelled) {
          return
        }
        // The cookie is dead or absent, which is the server's answer to
        // "is anyone signed in". The copy is dropped to match.
        removeAuthUser()
        setUser(null)
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function signIn(username: string, password: string) {
    const data = await authLogin(username, password)
    setAuthUser(data.user)
    setUser(data.user)
  }

  function adoptSession(data: AuthResponse) {
    setAuthUser(data.user)
    setUser(data.user)
  }

  function signOut() {
    removeAuthUser()
    setUser(null)
    // Ask the server to expire the cookie as well, otherwise the
    // httpOnly session survives this logout.
    void fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    }).catch(() => {
      // A failed logout call leaves the cookie in place; the next
      // request then re-adopts the session, which is the safe failure.
    })
  }

  return (
    <AuthContext.Provider value={{ user, loading, signIn, adoptSession, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)

  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider")
  }

  return ctx
}
