/**
 * The stored user is not a capability, so these tests pin the two
 * properties that keep it that way: a tampered or malformed value reads
 * as signed out, and the shape survives a round trip.
 */

import { beforeEach, describe, expect, it } from "vitest"

import { getAuthUser, removeAuthUser, setAuthUser } from "./auth"

const user = { id: 7, username: "founder", role: "admin" as const }

beforeEach(() => {
  window.localStorage.clear()
})

describe("setAuthUser and getAuthUser", () => {
  it("round-trips a valid user", () => {
    setAuthUser(user)
    expect(getAuthUser()).toEqual(user)
  })

  it("reads a missing value as signed out", () => {
    expect(getAuthUser()).toBeNull()
  })

  it("reads malformed JSON as signed out rather than throwing", () => {
    window.localStorage.setItem("aida_user", "{not json")
    expect(getAuthUser()).toBeNull()
  })

  it("rejects a user whose role is not one the API can issue", () => {
    // Editing this value in devtools grants nothing: the role is re-read
    // server-side on every request. Reading it back must not resurrect a
    // role the backend never sent, or the shell would render controls
    // that every request then refuses.
    window.localStorage.setItem(
      "aida_user",
      JSON.stringify({ id: 1, username: "x", role: "root" }),
    )
    expect(getAuthUser()).toBeNull()
  })

  it("rejects a user with a non-numeric id", () => {
    window.localStorage.setItem(
      "aida_user",
      JSON.stringify({ id: "1", username: "x", role: "admin" }),
    )
    expect(getAuthUser()).toBeNull()
  })

  it("does not store a token, because there is none to store", () => {
    setAuthUser(user)
    const raw = window.localStorage.getItem("aida_user") ?? ""
    expect(raw).not.toMatch(/token|jwt|Bearer/i)
  })
})

describe("removeAuthUser", () => {
  it("clears the stored user", () => {
    setAuthUser(user)
    removeAuthUser()
    expect(getAuthUser()).toBeNull()
  })

  it("is safe when nothing is stored", () => {
    expect(() => removeAuthUser()).not.toThrow()
    expect(getAuthUser()).toBeNull()
  })
})
