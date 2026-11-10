/**
 * The display formatters are a port of Jinja filters, and a page renders
 * whatever these return. A regression here is invisible in the UI until a
 * user reads a date and sees the wrong one, so the exact strings are
 * pinned rather than the shapes.
 */

import { describe, expect, it } from "vitest"

import { fmtDate, fmtDateTime, humanStatus, plural, titleKeepUnderscores } from "./format"

describe("fmtDateTime", () => {
  it("renders the Jinja %Y-%m-%d %H:%M form", () => {
    expect(fmtDateTime("2026-10-18T03:40:00")).toBe("2026-10-18 03:40")
  })

  it("returns an empty string rather than 'null' for a missing value", () => {
    expect(fmtDateTime(null)).toBe("")
    expect(fmtDateTime(undefined)).toBe("")
    expect(fmtDateTime("")).toBe("")
  })
})

describe("fmtDate", () => {
  it("keeps only the date part", () => {
    expect(fmtDate("2026-10-18T03:40:00")).toBe("2026-10-18")
    expect(fmtDate("2026-10-18")).toBe("2026-10-18")
  })

  it("returns an empty string for a missing value", () => {
    expect(fmtDate(null)).toBe("")
  })
})

describe("humanStatus", () => {
  it("converts the machine status to display wording", () => {
    expect(humanStatus("at_risk")).toBe("At Risk")
    expect(humanStatus("on_track")).toBe("On Track")
    expect(humanStatus("blocked")).toBe("Blocked")
  })

  it("does not capitalise after a hyphen, because the domain never uses one", () => {
    // The regex splits on whitespace only, so a hyphenated value keeps its
    // second word untouched. Pinned so a later "fix" to the regex is a
    // deliberate decision rather than an accident.
    expect(humanStatus("a-b")).toBe("A-b")
  })

  it("returns an empty string for a missing value", () => {
    expect(humanStatus(null)).toBe("")
    expect(humanStatus(undefined)).toBe("")
  })
})

describe("titleKeepUnderscores", () => {
  it("capitalises each underscore-separated word but keeps the separator", () => {
    // The history table renders event types this way: manual_resolve
    // becomes Manual_Resolve, not Manual Resolve.
    expect(titleKeepUnderscores("manual_resolve")).toBe("Manual_Resolve")
    expect(titleKeepUnderscores("created")).toBe("Created")
  })
})

describe("plural", () => {
  it("adds an s for every count but one", () => {
    expect(plural(0, "risk")).toBe("0 risks")
    expect(plural(1, "risk")).toBe("1 risk")
    expect(plural(2, "risk")).toBe("2 risks")
  })
})
