# Security Policy

## Supported Versions

Only the latest state of the `main` branch is supported with security fixes. There are no maintained backport branches, so older commits and images built from them do not receive patches. Upgrade to the current `main` before reporting issues that may already be fixed.

| Version | Supported |
| --- | --- |
| Latest `main` | Yes |
| Any older commit or release | No |

## Scope

This policy covers the application code in this repository:

- The FastAPI JSON API served by `api.py`: authentication and user management, projects, meetings, the document parsing pipeline, project memory and consolidation, history, reports, the review queue, and metrics.
- The React 19 and TypeScript frontend in `frontend/`, including how it handles tokens, roles, and API error responses.
- The NVIDIA build integration (request routing, response schema validation with pydantic, and retry handling).
- The Alembic migrations and database schema in `migrations/`.

## Out of Scope

The following are not treated as vulnerabilities in this project:

- Self-hosted deployments that still run unchanged default credentials, such as the `postgres`/`postgres` database user and password from `compose.yml`, the placeholder `JWT_SECRET_KEY`, or the default Grafana admin password. Change these before exposing a deployment to any network. Deployments running the documented defaults are considered unconfigured, not vulnerable.
- The hardening the project itself declares as missing. The README states the current implementation is suitable for local development and experimentation and is not production-ready without additional security, observability, and reliability work. Gaps in that declared scope are tracked as normal issues, not security reports.
- Vulnerabilities in third-party dependencies (FastAPI, React, SQLAlchemy, PyJWT, Vite, and others) unless a concrete exploit path through this application's code is demonstrated. Report dependency issues to their upstream maintainers and mention them here only when this project is affected.
- Rate limiting or quota problems on the NVIDIA build free tier, including spend on a user-supplied API key.
- Findings from automated scanners without a reproducible case and an explained impact.
- Social engineering, phishing, or physical attacks against maintainers or users.
- Missing transport security on self-managed infrastructure, since this project does not control deployment networking.

## Reporting a Vulnerability

Do not open a public issue for a suspected security problem, and do not discuss it in public pull requests or discussions.

Report privately through GitHub Security Advisories:

- https://github.com/wladimirkarpicki/ai-delivery-assistant/security/advisories/new

Include as much of the following as you can:

- A description of the vulnerability and the impact you believe it has.
- The affected component, such as an API route, a frontend page, or a module name.
- Steps to reproduce, with a proof of concept when possible.
- The commit or version you tested against.
- Any suggested fix or mitigation.

## What to Expect

We acknowledge a new report within 72 hours and aim to provide an initial assessment within 7 days. We may ask for additional detail while investigating. Once a fix is ready we coordinate disclosure, publish the advisory, and credit reporters who want attribution.

## Known Gaps

Both entries this section used to hold are closed. They are recorded here
rather than deleted, because the state they describe is the state a reader
is most likely to assume and it is worth saying explicitly that it is not
the case.

### Token revocation survives a restart

Revocation used to be recorded in a set inside the process, so after a
restart a signed-out token worked again until its own expiry, up to
`TOKEN_TTL_HOURS`. That set is now a cache rather than the record: a
logout writes the token's id and its expiry to a `revoked_tokens` table,
and the check reads the cache first and the table on a miss, so a restart
no longer re-accepts a token. Rows whose token has already lapsed are
pruned on logout rather than accumulating.

One genuine limitation remains, and it is the same class: the pruned set is
per process, so a token revoked by one worker is not visible to another
until that worker commits the row, which it does on the next logout or
check that reaches it. With a single worker behind the compose stack that
is not reachable. Running more than one worker needs the check to read the
table without a cache in front of it.

Where this has actually been exercised, because a test suite on SQLite
cannot show it: the migration chain applied to a real PostgreSQL, the
`revoked_tokens` table exists with `jti` and `expires_at` as a
`timestamptz`, and a signed-out token was refused by a process started
after the one that revoked it, with the row present as the source of the
answer. The compose stack itself has not been rebuilt and shown to boot
from `schema.sql` with the table present; that part is still outstanding
and is recorded in `docs/REFACTORING-PLAN.md`.

### The activity timeline reports every month

`month_counts` used to read every `created_at` into Python and count there,
which is O(rows) per request on a table that grows forever. It was then
bounded to a trailing 24 months, which fixed the cost and silently dropped
older months, so a month older than the window looked identical to a month
with nothing in it. The query now aggregates in the database with `GROUP BY`,
so the work is proportional to how many months exist rather than how many
rows, and every month with data is reported.

The exercise here is worth recording: the first fix traded one silent bug
for another, and the test written for it pinned the wrong behaviour. The
test asserted that an old month was absent, which is what made the loss
look correct.

## What is inherently limited

This is a prototype for one user on one machine. The following are not
defects but consequences of that scope, listed so nobody has to discover
them:

- There is no multi-user authority model beyond the two roles in the
  `users` table, and no audit trail of who read what.
- The LLM provider is a single fixed model. There is no fallback provider,
  so a provider outage means no analysis until it returns.
- The consolidation pipeline is the correctness-critical part and it is
  the least covered by tests, because the interesting cases need a real
  model to produce them.
- There is no deployment artefact beyond the compose file, no migration
  rollback story beyond `alembic downgrade`, and no backup or restore
  procedure.
