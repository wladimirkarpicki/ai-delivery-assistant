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

## Landed this round, each verified

| Commit | What was proven |
|---|---|
| `0ad8e32` | `add_meeting` no longer blocks the event loop; provider failures caught instead of 500 |
| `8d385b9` | 7 unreachable definitions removed, 45 lines |
| `c9aaf97` | Initial bundle 703,743 to 263,184 bytes measured, -62.6 % |
| `b2fa8f5` | NOT NULL and varchar(n) both verified enforced on the live PostgreSQL; `projects.name` and `meetings.source_filename` clamped |
| `bfc01bc` | Flash notices announced with `role=alert`; skip link added; typecheck and build exit 0 |

## Found and fixed during verification: credential drift between the env and the volume

The stack was healthy and `/api/health` answered 200, but every login
returned 500. The cause was not code:

`POSTGRES_PASSWORD` only takes effect when the data directory is empty.
The volume had already been initialised, so the environment variable was
cosmetic and the real password was whatever the first init used. The app
container was configured with the env value and could not authenticate.

The failure is worth recording because it is invisible to the usual
checks. `pg_hba.conf` in the postgres image grants `trust` on the unix
socket and on `127.0.0.1`, so connecting *from inside the database
container* succeeds with any password, including a wrong one. Two
verification runs reported success that way before the app container,
which connects over the Docker bridge and hits `scram-sha-256`, showed the
real state.

The fix was `ALTER USER postgres WITH PASSWORD` to the value the app
expects, after which the full path succeeded: login 200 with a cookie,
project create 201, meeting submit 201, and `/metrics` reporting the rows
written.

The standing lesson: verify a database change by connecting the way the
application does, never from inside the database container.

## Explicit non-goals

- No dependency-injection framework, no plugin system, no event bus. The
  monolith is the right shape for a single-user prototype and the cost of
  those is not paid back here.
- No distributed tracing. The request id is per-process and the app has
  no tracing backend; adding one is decoration.
- No database sharding or read replicas.
- No rewrite of the consolidation algorithm.
- No change to `project_memory.py` or `matching.py`.
