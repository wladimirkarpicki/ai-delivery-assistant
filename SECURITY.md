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
- The OpenRouter integration (request routing, response schema validation with pydantic, and retry handling).
- The Alembic migrations and database schema in `migrations/`.

## Out of Scope

The following are not treated as vulnerabilities in this project:

- Self-hosted deployments that still run unchanged default credentials, such as the `postgres`/`postgres` database user and password from `compose.yml`, the placeholder `JWT_SECRET_KEY`, or the default Grafana admin password. Change these before exposing a deployment to any network. Deployments running the documented defaults are considered unconfigured, not vulnerable.
- The hardening the project itself declares as missing. The README states the current implementation is suitable for local development and experimentation and is not production-ready without additional security, observability, and reliability work. Gaps in that declared scope are tracked as normal issues, not security reports.
- Vulnerabilities in third-party dependencies (FastAPI, React, SQLAlchemy, PyJWT, Vite, and others) unless a concrete exploit path through this application's code is demonstrated. Report dependency issues to their upstream maintainers and mention them here only when this project is affected.
- Rate limiting or quota problems on the OpenRouter free tier, including spend on a user-supplied API key.
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

None currently open. The bearer-token exposure listed here previously is closed: the session now travels in an `httpOnly`, `SameSite=strict` cookie with `Secure` when the request is TLS, the client no longer reads or stores a token, a Content-Security-Policy without `unsafe-inline` in `script-src` blocks inline script execution, and `/api/auth/logout` revokes the token's id rather than only clearing the cookie in one browser.
