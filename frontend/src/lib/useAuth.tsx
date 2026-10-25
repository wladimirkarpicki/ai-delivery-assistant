/**
 * Auth context: resolves the stored bearer token into the live
 * account on mount, signs users in and out.
 *
 * The API re-reads the account on every request, so this state is a
 * convenience copy: the header badge, the RequireAuth gate, and the
 * admin-only routes read it. A dead token is dropped by lib/api.ts
 * (401 -> /login) before this state could go stale visibly.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"

import { authLogin, getMe, type AuthResponse } from "./api"
import { getToken, removeToken, setToken, type AuthUser } from "./auth"

interface AuthState {
  user: AuthUser | null
  loading: boolean
  /** Sign in with credentials; throws ApiError on refusal. */
  signIn: (username: string, password: string) => Promise<void>
  /** Adopt a session the setup bootstrap just issued. */
  adoptSession: (data: AuthResponse) => void
  /** Drop the token and forget the account. */
  signOut: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = getToken()

    if (!token) {
      setLoading(false)
      return
    }

    getMe()
      .then(setUser)
      .catch(() => {
        removeToken()
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  async function signIn(username: string, password: string) {
    const data = await authLogin(username, password)
    setToken(data.access_token)
    setUser(data.user)
  }

  function adoptSession(data: AuthResponse) {
    setToken(data.access_token)
    setUser(data.user)
  }

  function signOut() {
    removeToken()
    setUser(null)
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
