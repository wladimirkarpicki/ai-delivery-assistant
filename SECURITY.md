# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | ✅ Yes             |

## Reporting a Vulnerability

If you discover a security vulnerability in ai-delivery-assistant, please report it responsibly:

1. **Do not create a public issue** — this could expose the vulnerability before it's fixed.
2. **Email** the maintainers directly at: **security@ai-delivery-assistant.example.com**
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

| Severity | Initial Response | Target Fix |
| -------- | ---------------- | ---------- |
| Critical | 24 hours         | 72 hours   |
| High     | 48 hours         | 1 week     |
| Medium   | 1 week           | 2 weeks    |
| Low      | 2 weeks          | Next release |

We will acknowledge receipt within the initial response window and keep you informed of progress.

## Security Measures

This project implements:

- **SAST** — Bandit runs on every push/PR (GitHub Actions)
- **SCA** — Safety scans Python dependencies weekly
- **CodeQL** — GitHub Code Scanning with SARIF uploads
- **Dependabot** — Weekly dependency update PRs
- **Secrets management** — `.env` in `.gitignore`, central `config_loader.py`
- **Input validation** — File upload whitelist, size limits, type checks
- **SQL injection prevention** — SQLAlchemy ORM / parameterized queries
- **XSS prevention** — React auto-escaping, no `dangerouslySetInnerHTML`
- **Audit logging** — Immutable `HistoryEvent` for all data mutations

## Scope

This policy applies to:
- Core backend (`api.py`, `models.py`, `database.py`, `project_memory.py`, etc.)
- Frontend (`frontend/` React + TypeScript)
- Infrastructure (GitHub Actions, Docker, deployment configs)

Third-party dependencies are covered by Dependabot alerts and weekly Safety scans.

## Disclosure

After a fix is released, we will:
1. Publish a GitHub Security Advisory
2. Credit the reporter (unless anonymity requested)
3. Detail the vulnerability and fix in release notes