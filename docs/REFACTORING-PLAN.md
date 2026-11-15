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
| Router split of `api.py` | 2212 lines to 441, split across four routers and five support modules |
| Token revocation persisted to a table | An in-memory set meant a logout stopped working after a restart |
| The activity timeline aggregates in SQL | It read every row into Python and counted there; bounding it to 24 months dropped history silently |
| `project_memory.py` consolidation cycles collapsed | Three near-identical copies, and a 441-line function |
| Frontend test suite | Zero tests; a regression in what a page rendered was caught by nobody |
| All 8 dependabot PRs resolved | Two needed the change applied on `main` with a real code fix, not a merge |

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

## Closed on 2026-11-15: the compose path rebuilt from HEAD and proven

Token revocation is persisted to a `revoked_tokens` table and the test
suite passes, but the suite runs on SQLite. That is the dialect which
hides exactly this bug class: `session.scalar` typing differences, NOT
NULL enforcement and varchar widths all behave differently there, and two
of those three have already bitten this project once.

The live container also had a second reason it could not prove anything:
its database volume was already initialised, so `schema.sql` was never
loaded and the table did not exist in the running database at all. That
is the state described below under the credential drift, and it is why
the container path was never a proof of anything.

**Correction (2026-11-15), dated rather than silently rewritten.** The
disk figures above were stale for this host even then: `C:` had ~93 GiB
free of 159 GiB, and no `postgresql-x64-18` service existed at all. The
real blocker was Docker's WSL precondition — no WSL distribution was
installed, so the engine answered `unable to start` until the owner
installed WSL (engine 29.9.3, Compose v5.7.0). Kept in the record,
because a wrong root cause left standing is worse than no record.

Two things are deliberately not deleted to find it, because neither is
mine to remove: `hermes` (4.97 GB, a third-party agent with an update lock
dated today) and the OS directories `WinSxS` (8.36 GB) and `System32`
(4.81 GB).

**Proven against the host PostgreSQL 18.4 instead.** Docker could not
start, so the verification ran against the host server, which is the same
engine class and a real PostgreSQL rather than the test harness:

- `alembic upgrade head` on it applied `c2f6b8d4a1e9` (users) and
  `d4e7f1a2b3c5` (revoked tokens) and the database ended at `d4e7f1a2b3c5`,
  which also exercises the migration chain rather than only `schema.sql`.
- `revoked_tokens` exists with `jti varchar` and
  `expires_at timestamp with time zone`, matching the model.
- The live probe: setup 200, login 200, token 189 chars, `/api/auth/me`
  200; logout 200; `/api/auth/me` 401 in the same process; the process was
  killed and a new one started with an empty cache, and `/api/auth/me`
  401 again, while login still worked. The row was in the table, so the
  answer came from PostgreSQL and not from memory.

The remaining gap was therefore not the fix but the artifact. On
2026-11-15 it was closed, against main at
`444ec3b56608aa091e1e2c57935119806b129961`. That sha is pushed:
`origin/main` equals it (a plain `git push` moves the remote on this
host — `gh` is absent, but push does not need it). The local-only piece
is the evidence branch `w1-compose-verification` (one docs commit on
top of that sha, unpushed), delivered to the owner as a patch.
Commands and full outputs live in `evidence/` (gitignored, local):

- `docker builder prune -af` (build cache was already 0B on this host),
  `docker pull node:22-alpine` and `python:3.13-slim` (fresh digests),
  `docker compose build` from that sha — exit 0, image
  `ai-delivery-assistant-app:latest`.
- `docker compose down -v` (drops `pgdata_ai2`), `docker compose up -d`:
  the db logged `running /docker-entrypoint-initdb.d/schema.sql` at
  13:33:43Z and both containers came up `healthy`.
- `revoked_tokens` verified the way the app connects — from inside the
  **app** container over TCP to `db:5432` with scram-sha-256, never from
  the db container, whose socket is `trust`: table present; columns
  `jti character varying(64) NOT NULL` and
  `expires_at timestamp with time zone NOT NULL`.
- Full probe through the published port 8001: health 200, setup 200,
  login 200 (cookie), `/api/auth/me` 200 with that token, project create
  201, logout 200, `/api/auth/me` **401 "Session has ended."**,
  `docker compose restart app`, `/api/auth/me` **401 again** with the
  process cache empty and one row visible in the table (jti, expiry 12h
  out) — revocation is answered from PostgreSQL, not from memory.
  `/metrics` 200 with `aida_projects 1`.
- `meeting_submit` returned **400, not 201**: no NVIDIA_API_KEY exists
  on this host (placeholder in `.env`), the analysis call fails and the
  handler rolls back cleanly ("The meeting was not saved"). An
  owner-supplied key closes that step; it was not fabricated.
- CI re-fetched 2026-11-15 via GitHub REST on the build sha itself,
  `444ec3b56608aa091e1e2c57935119806b129961`: **11/11 check runs
  success** — the 8 `security.yml` jobs (Static Analysis (Bandit),
  Dependency Scan (Safety), Code Quality (Ruff), Type Checking
  (Mypy), Tests (Pytest), Migrations (Alembic), Frontend Audit (pnpm
  audit), Frontend Typecheck and Build) plus 3 CodeQL Analyze runs
  (python, javascript-typescript, actions), all started
  2026-11-15T13:09Z. Background: the previous pushed sha
  `08c9bba663ee1da3091564c4ac3e17d182cdfae2`, one behind `origin/main`
  now, shows 14/14 across the same 11 jobs (duplicate CodeQL re-runs).

**Found during this run, recorded and not fixed (out of scope here):**
`schema.sql` creates `revoked_tokens` **without** the primary key. The
model and the migration `d4e7f1a2b3c5` both declare `jti` as the PK and
the schema's own comment says a check is "one index lookup", but
`schema.sql` lines 398-401 create the table with two NOT NULL columns
and no constraint — verified live: `pg_indexes` for the table returns
empty on a fresh container, and the container never runs alembic, so
the stack does not get the model's index.

## One elevated command left: the PostgreSQL bind

`listen_addresses` on the host PostgreSQL 18 is `'*'`, so it listens on
`0.0.0.0` and `::`. The config has been edited to `'localhost'` with a
backup at `_db_backups/postgresql18_conf_20261111_backup.conf`, and the
surrounding structure is intact: the edit added three comment lines and
the value, and `port` and the directives after it are unchanged.

Two things stopped it taking effect, both of which needed elevation:

- `Restart-Service postgresql-x64-18` fails with `Cannot open
  postgresql-x64-18 service on computer '.'`, which is a permissions
  error, not a state error. An earlier restart that appeared to succeed
  did not: it was run with `-ErrorAction SilentlyContinue`, so the same
  failure was swallowed. That is why the server kept reporting
  `listen_addresses = '*'` right after.
- `listen_addresses` is a postmaster parameter. `pg_reload_conf()` does
  not apply it, so there is no unprivileged path.

To finish it, from an elevated shell:

```
Restart-Service postgresql-x64-18
```

then confirm the server reports `localhost` and the listening sockets
show `::1` only, not `0.0.0.0`.

Until then the reachability picture is unchanged and should not be
overstated: `pg_hba.conf` allows only `local`, `127.0.0.1/32` and
`::1/128`, all with `scram-sha-256`, and there is no inbound firewall
rule for 5432, so the port is not reachable from the network. The bind
is a latent gap rather than a live one.

## Explicit non-goals

- No dependency-injection framework, no plugin system, no event bus. The
  monolith is the right shape for a single-user prototype and the cost of
  those is not paid back here.
- No distributed tracing. The request id is per-process and the app has
  no tracing backend; adding one is decoration.
- No database sharding or read replicas.
- No rewrite of the consolidation algorithm.
- No change to `project_memory.py` or `matching.py`.
