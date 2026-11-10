/**
 * The auth context is the gate in front of every page. The properties
 * that matter are the ones a user would notice: a session the server
 * refuses must not stay adopted, and logging out must clear both the
 * local copy and the server's cookie.
 */

import { act, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AuthProvider, useAuth } from "./useAuth"

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
  window.localStorage.clear()
})

function Probe() {
  const { user, loading, signOut } = useAuth()
  return (
    <div>
      <span data-testid="loading">{loading ? "loading" : "ready"}</span>
      <span data-testid="user">{user ? user.username : "none"}</span>
      <button onClick={signOut}>sign out</button>
    </div>
  )
}

describe("AuthProvider", () => {
  it("adopts the account the server reports", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: 1, username: "founder", role: "admin" }),
    } as unknown as Response)

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("ready"),
    )
    expect(screen.getByTestId("user").textContent).toBe("founder")
  })

  it("drops the cached copy when the server refuses the cookie", async () => {
    // The cached identity exists so the shell does not flash a signed-out
    // layout, but the server is the authority: if it answers 401 the local
    // copy must go, or a user whose session died keeps seeing their name.
    window.localStorage.setItem(
      "aida_user",
      JSON.stringify({ id: 1, username: "stale", role: "user" }),
    )
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Invalid or expired token." }),
    } as unknown as Response)

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("ready"),
    )
    expect(screen.getByTestId("user").textContent).toBe("none")
    expect(window.localStorage.getItem("aida_user")).toBeNull()
  })

  it("tells the server to drop the cookie on sign out", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: 1, username: "founder", role: "user" }),
    } as unknown as Response)

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("founder"),
    )

    act(() => {
      screen.getByRole("button", { name: "sign out" }).click()
    })

    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("none"),
    )
    // Without this call the httpOnly session survives the logout and the
    // next request re-adopts it.
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    })
  })
})
