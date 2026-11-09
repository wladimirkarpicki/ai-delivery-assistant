# Refactoring Plan

Status: **partial**. This document currently covers only the areas the
second-round audit actually produced findings for. Three of four audit
areas are still running; when they report, items for them are added here
rather than this document being rewritten.

## Constraints set by the owner

- `project_memory.py` and `matching.py` are **not** refactored. They are
  isolated enough and the risk is not worth the gain. Their findings, if
  any, are documented and left.
- PostgreSQL is the real target. SQLite is a test harness, and a fix that
  only works on SQLite is not a fix.
- Every item must land with CI green and branch protection intact.

## Ordering rule

Value divided by risk. Items that unblock later items come first even
when their own value is lower.

## Done (this round and the previous one)

| Item | Why it was first |
|---|---|
| Leaked `.env` purged from history and force-pushed | A live credential in a public repo outranks everything |
| `/api/auth/setup` gated by a one-time bootstrap token | An unauthenticated admin bootstrap is an open door |
| No predictable secrets in `.env.example` or `compose.yml` | A default that looks fine is worse than a missing one |
| `schema.sql` made PostgreSQL 16 compatible | Two PG18-only lines made a fresh container unbootable |
| CI gates made real: `|| true` removed from 3 jobs, `pytest` and `tsc` jobs added | A badge that cannot go red is decoration |
| Session moved to an `httpOnly` cookie, with a CSP and logout revocation | An XSS could read the token out of localStorage |
| `month_counts` bounded to 24 months | The read grew for the life of the database |
| `/api/dashboard` N+1 removed (302 to 8 queries) | Same class, smaller |
| OpenRouter replaced by the NVIDIA build gateway | The provider the app could actually reach |
| `api.py` monitors/observability: `telemetry.py`, a log format, a request id | A failure nobody can find in a log is not observable |
| `main` branch protected: 10 required checks, force-push and deletion blocked | Direct pushes are how the leak would have been reintroduced |

## In progress

| Item | State |
|---|---|
| Central logging and request correlation | Landed in `6918a7b`, CI #90 8/8, verified live |
| Second-round audit: PostgreSQL correctness | Agent running |
| Second-round audit: architecture and code quality | Agent running |
| Second-round audit: frontend | Agent running |
| Second-round audit: observability and process | Delivered; findings folded into `6918a7b` |

## Not started

| Item | Value | Blocked by |
|---|---|---|
| Router split of `api.py` | The user's stated top candidate | The architecture audit's concrete blueprint |
| Dependency merge (10 dependabot PRs) | Unblocks security patches | Branch protection already on; each merge needs a green run |
| Asset split of the frontend bundle | Load time | The frontend audit's measured composition |
| Frontend test setup | Regression safety | The frontend audit's proposal |

## Explicit non-goals

- No dependency-injection framework, no plugin system, no event bus. The
  monolith is the right shape for a single-user prototype and the cost of
  those is not paid back here.
- No distributed tracing. The request id is per-process and the app has
  no tracing backend; adding one is decoration.
- No database sharding or read replicas.
- No rewrite of the consolidation algorithm.
- No change to `project_memory.py` or `matching.py`.
