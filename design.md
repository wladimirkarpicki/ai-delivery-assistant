# Design — AI Delivery Assistant

A locked visual system for a delivery-operations workspace. Pages preserve the app's routes and data; the system changes only their presentation.

## Genre

Modern-minimal, Cobalt register: a cool, precise operational interface rather than a generic SaaS dashboard.

## Macrostructure family

- App pages: **Workbench** — project context, a delivery signal, and a prioritized operational queue.
- Content pages: **Long Document** — a readable record with metadata and a chronological evidence trail.
- Marketing pages: not applicable.

## Theme

Cool engineered paper, charcoal ink, hairline rules, and one restrained cobalt signal. Values and all reusable spacing, type, motion, and radius tokens live in `static/tokens.css`.

Dark mode keeps the same register on engineered graphite: `tokens.css` re-declares the colour tokens under `:root[data-theme="dark"]`, the default follows the system colour scheme, the header toggle persists the visitor's choice in `localStorage`, and pages without JavaScript stay on the light theme.

## Typography

- Display: Space Grotesk, upright, 500–700
- Body: IBM Plex Sans, 400–600
- Mono: JetBrains Mono, 400–600 for timestamps, model names, and status labels

## Motion and interaction

No decorative reveals. Controls use short colour/position changes only; focus rings are immediate and visible. Reduced-motion users receive static interfaces.

## What pages must share

The wordmark, cobalt accent, typography, tight 6–10px radii, hairline surfaces, and quiet inline footer.

## What pages may differ on

Operational pages may foreground a decision queue; record pages may foreground a prose/timeline reading flow.
