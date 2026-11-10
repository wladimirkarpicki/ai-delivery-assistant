# Changelog

Major changes only. Every commit lives in `git log`; what this file records is
the round of work a reader would need to know about to understand the state
of the project. Descriptions are of what changed and why, not of individual
commits.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [SemVer](https://semver.org/) with an `-alpha` suffix while
it is a prototype.

## [Unreleased]

### Added

- Central logging configuration: one formatter (timestamp, level, logger
  name) and a `LOG_LEVEL` setting, plus a per-request correlation id echoed
  as `X-Request-ID`, so a user-reported failure can be found in the log.
- `revoked_tokens` table with a migration, so a logout survives a process
  restart instead of only this process.
- `docs/REFACTORING-PLAN.md`: what has been done, what is in progress, what
  is not started, and an explicit non-goals list.

### Changed

- `api.py` is no longer a monolith: 2212 lines down to 441, split into
  `api_auth.py`, `api_deps.py`, `api_memory.py`, `api_analytics.py`,
  `api_serializers.py`, `api_uploads.py` and four routers
  (`api_routers_auth`, `api_routers_items`, `api_routers_meetings`,
  `api_analytics`). What is left in `api.py` is the factory, CORS and
  security middleware, the request-scope middleware, the SPA fallback and
  the health route.
- The auth state that made the split impossible now lives on `app.state`
  rather than in closures over `create_app`, and is read per request. A
  module-level global was the alternative and was rejected on evidence:
  `secret_key` is generated per `create_app` call, the test suite builds
  about ten apps in one process, and a global would have made all of them
  share one signing key while every test kept passing.
- `project_memory.py`: the three near-identical create-or-update cycles are
  one skeleton driven by a spec table, and the 441-line consolidation
  applier is a dispatcher plus four named branches.
- `add_meeting` is a sync endpoint. It was `async def` with a blocking body
  making LLM calls with a 180 s timeout each, so one submission stalled
  every request including `/api/health`.
- The activity timeline aggregates in the database with `GROUP BY` rather
  than reading every row into Python. It was previously bounded to 24
  months, which fixed the cost and dropped older months.
- The frontend loads pages on demand. The initial bundle went from 703,743
  to 263,184 bytes measured, with the charting library moved off the first
  screen.
- Error notices are announced to a screen reader and a skip link was added.

### Fixed

- PostgreSQL 16 compatibility of `schema.sql`: two statements produced by
  `pg_dump` 18 (`transaction_timeout`, `\unrestrict`) aborted the schema
  load, so a fresh container never came up.
- Exception text no longer reaches the client on provider or database
  failures, including through the consolidation fallback warning.
- `projects.name` and `meetings.source_filename` are clamped to their
  column widths; they were the two operator-controlled columns the
  clamping map did not cover.
- The README had been double-encoded, leaving mojibake dashes and arrows.

### Security

- Sessions travel in an `httpOnly` cookie with `SameSite=strict`, a CSP
  without `unsafe-inline` in `script-src`, token revocation on logout, and
  a one-time bootstrap token for the first admin.
- A leaked key was purged from git history and rotated.
- Exception text no longer reaches the client on a provider or database
  failure, including through the consolidation fallback warning, which is
  the flow GitHub flagged as `py/stack-trace-exposure`.
- `projects.name` and `meetings.source_filename` are clamped to their
  column widths. They were the two operator-controlled columns the clamping
  map did not cover.

### Testing

- The frontend has a real suite: 27 tests over 5 files, run by the CI
  frontend job, so a regression in what a page renders is a failing build
  rather than something a human notices.
- The backend suite is 105 tests. The `ExceptionExposureTests` and
  `RevocationPersistenceTests` classes exist because both bugs they cover
  were invisible in a green suite first.

## [0.5.0] - 2026-08-01

### Added

- Docker Compose stack with PostgreSQL 16, Prometheus metrics and a
  Grafana datasource.
- Meeting analysis with a two-stage pipeline: extraction, then
  consolidation of findings against existing project memory.
- Review queue for findings the guardrails will not apply silently.

### Changed

- The application was rewritten from Flask to FastAPI with a React SPA.
- Typed SQLAlchemy 2.0 models with `Mapped` annotations.
