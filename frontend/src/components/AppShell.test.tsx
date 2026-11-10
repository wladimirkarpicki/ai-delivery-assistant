/**
 * The 404 body is also the "record not found" screen, so it is where a
 * lost user lands. It has to offer a way back that a keyboard and a
 * screen reader can both reach.
 */

import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { NotFoundBody } from "../pages/NotFound"

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe("NotFoundBody", () => {
  it("renders a level-1 heading, so a screen reader announces the page", () => {
    renderWithRouter(<NotFoundBody />)
    expect(
      screen.getByRole("heading", { level: 1, name: /page not found/i }),
    ).toBeInTheDocument()
  })

  it("offers a real link back to the projects list", () => {
    renderWithRouter(<NotFoundBody />)
    // A link, not a div with a click handler: keyboard and screen reader
    // both reach it for free.
    expect(screen.getByRole("link", { name: /back to projects/i })).toHaveAttribute(
      "href",
      "/projects",
    )
  })

  it("names the error rather than showing a bare number", () => {
    renderWithRouter(<NotFoundBody />)
    expect(screen.getByText(/error 404/i)).toBeInTheDocument()
    expect(screen.getByText(/does not exist or was moved/i)).toBeInTheDocument()
  })
})
