/**
 * The API client's contract with the backend, tested through the exported
 * functions rather than the private request helper: the cookie travels on
 * every call, a dead session sends the user to sign-in, and the error text
 * the UI shows comes from the server's field rather than the status line.
 */

import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, getProjects } from "./api"

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => body,
  } as unknown as Response
}

describe("credentials", () => {
  it("sends the httpOnly session cookie on every request", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ projects: [] }))

    await getProjects()

    // credentials: "include" is what carries the cookie; without it the
    // server sees an anonymous request on every call and the app looks
    // broken only after login.
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" })
  })
})

describe("a dead session", () => {
  it("redirects to sign-in on a 401 instead of leaving a blank page", async () => {
    const assign = vi.fn()
    // jsdom has no navigation; assign is the seam the client uses.
    Object.defineProperty(window, "location", {
      value: { assign },
      writable: true,
    })

    fetchMock.mockResolvedValue(jsonResponse({ detail: "Invalid or expired token." }, 401))

    await expect(getProjects()).rejects.toBeInstanceOf(ApiError)
    expect(assign).toHaveBeenCalledWith("/login")
  })
})

describe("error messages", () => {
  it("prefers the server's error field over the status line", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: "A project with this name already exists." }, 400),
    )

    // The user-facing sentence comes from the backend, so a 400 must not
    // surface as "400 Bad Request".
    await expect(getProjects()).rejects.toThrow(
      "A project with this name already exists.",
    )
  })

  it("falls back to detail when there is no error field", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Admin only." }, 403))

    await expect(getProjects()).rejects.toThrow("Admin only.")
  })
})
